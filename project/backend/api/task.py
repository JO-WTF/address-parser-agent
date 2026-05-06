import asyncio
from pathlib import Path
from typing import Dict

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.core import Agent
from task.manager import TaskManager
from tools.excel import ExcelTool

router = APIRouter()
manager = TaskManager()
excel = ExcelTool()
agent = Agent()
subscribers: Dict[str, set[asyncio.Queue]] = {}


async def publish(task_id: str, payload: dict):
    channels = subscribers.get(task_id, set())
    print(f"[WS] publish task={task_id}, subscribers={len(channels)}, payload={payload}")
    for q in channels:
        await q.put(payload)


class RunRequest(BaseModel):
    task_id: str
    address_field: str


@router.get("/headers/{task_id}")
def headers(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return {"headers": excel.read_headers(task.file_path)}


@router.post("/run")
async def run(req: RunRequest):
    task = manager.get_task(req.task_id)
    if not task:
        raise HTTPException(404, "task not found")
    manager.update_task(
        req.task_id,
        selected_column=req.address_field,
        address_field=req.address_field,
        status="running",
    )
    asyncio.create_task(process_task(req.task_id))
    return {"ok": True}


async def process_task(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        return
    try:
        print(f"[TASK] start processing task_id={task_id}")
        excel.copy_to_output(task.file_path, task.output_path)
        df = pd.read_excel(task.file_path).fillna("")
        total = len(df)
        manager.update_task(task_id, total_rows=total)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            latest = manager.get_task(task_id)
            if i < latest.current_row:
                continue
            text = str(getattr(row, latest.address_field, ""))
            print(f"[TASK] row={i}, text={text}")
            result = agent.extract_info(text)
            excel.write_result_row(latest.output_path, i + 1, result)
            progress = i / total if total else 1.0
            manager.update_task(task_id, current_row=i, progress=progress)
            await publish(task_id, {"progress": progress, "current": i, "total": total})
        print(f"[TASK] completed task_id={task_id}")
        manager.update_task(task_id, status="completed", progress=1.0)
        await publish(task_id, {"progress": 1.0, "status": "completed"})
    except Exception as e:
        print(f"[TASK] failed task_id={task_id}, error={e}")
        manager.update_task(task_id, status="failed", error=str(e))
        await publish(task_id, {"status": "failed", "error": str(e)})


@router.get("/task/{task_id}")
def get_task(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()


@router.get("/download/{task_id}")
def download(task_id: str):
    task = manager.get_task(task_id)
    if not task or not Path(task.output_path).exists():
        raise HTTPException(404, "result not found")
    return FileResponse(task.output_path, filename=f"{task_id}_result.xlsx")

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
from logger import get_logger

router = APIRouter()
manager = TaskManager()
excel = ExcelTool()
agent = Agent()
subscribers: Dict[str, set] = {}
event_buffers: Dict[str, list[dict]] = {}
logger = get_logger("api.task")


async def publish(task_id: str, payload: dict):
    buffer = event_buffers.setdefault(task_id, [])
    buffer.append(payload)
    if len(buffer) > 200:
        del buffer[:-200]

    channels = subscribers.get(task_id, set())
    logger.info("[WS] publish task=%s, subscribers=%s, payload=%s", task_id, len(channels), payload)
    dead = []
    for ws in channels:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        channels.discard(ws)


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
    total = await asyncio.to_thread(lambda: len(pd.read_excel(task.file_path).fillna("")))
    manager.update_task(
        req.task_id,
        selected_column=req.address_field,
        address_field=req.address_field,
        status="running",
        total_rows=total,
    )
    await publish(req.task_id, {"progress": 0, "current": 0, "total": total})
    asyncio.create_task(process_task(req.task_id))
    return {"ok": True, "total": total}


async def process_task(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        return
    try:
        logger.info("[TASK] start processing task_id=%s", task_id)
        await asyncio.to_thread(excel.copy_to_output, task.file_path, task.output_path)
        df = await asyncio.to_thread(lambda: pd.read_excel(task.file_path).fillna(""))
        total = len(df)
        manager.update_task(task_id, total_rows=total)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            latest = manager.get_task(task_id)
            if i < latest.current_row:
                continue
            text = str(getattr(row, latest.address_field, ""))
            logger.info("[TASK] row=%s, text=%s", i, text)
            result = await asyncio.to_thread(agent.extract_info, text)
            await asyncio.to_thread(excel.write_result_row, latest.output_path, i + 1, result)
            progress = i / total if total else 1.0
            manager.update_task(task_id, current_row=i, progress=progress)
            await publish(
                task_id,
                {
                    "progress": progress,
                    "current": i,
                    "total": total,
                    "text": text,
                    "result": result,
                },
            )
            await asyncio.sleep(0)
        logger.info("[TASK] completed task_id=%s", task_id)
        manager.update_task(task_id, status="completed", progress=1.0)
        await publish(task_id, {"progress": 1.0, "status": "completed"})
    except Exception as e:
        logger.exception("[TASK] failed task_id=%s, error=%s", task_id, e)
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

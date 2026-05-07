import asyncio
from pathlib import Path
from typing import Dict
import contextlib

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
running_jobs: Dict[str, asyncio.Task] = {}
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
        status="running",
        total_rows=total,
    )
    await publish(
        req.task_id,
        {
            "progress": float(task.progress or 0),
            "current": int(task.current_row or 0),
            "total": total,
            "status": "running",
        },
    )
    if req.task_id in running_jobs and not running_jobs[req.task_id].done():
        raise HTTPException(400, "task is already running")
    running_jobs[req.task_id] = asyncio.create_task(process_task(req.task_id))
    return {"ok": True, "total": total, "current": int(task.current_row or 0), "progress": float(task.progress or 0)}


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
            if i <= latest.current_row:
                continue
            text = str(getattr(row, latest.selected_column, ""))
            logger.info("[TASK] row=%s, text=%s", i, text)
            result = await asyncio.to_thread(agent.extract_info, text)
            await asyncio.to_thread(excel.write_result_row, latest.output_path, i + 1, result)
            progress = i / total if total else 1.0
            manager.update_task(
                task_id,
                current_row=i,
                progress=progress,
                contact_name=result.get("name", ""),
                contact_phone=result.get("phone", ""),
                contact_email=result.get("email", ""),
                company_name=result.get("company_name", ""),
                address_detail=result.get("address", ""),
                province=result.get("province", ""),
                city=result.get("city", ""),
                country=result.get("country", ""),
                delivery_note=result.get("remark", ""),
            )
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
    except asyncio.CancelledError:
        logger.info("[TASK] stopped task_id=%s", task_id)
        manager.update_task(task_id, status="stopped")
        await publish(task_id, {"status": "stopped"})
        raise
    except Exception as e:
        logger.exception("[TASK] failed task_id=%s, error=%s", task_id, e)
        manager.update_task(task_id, status="failed", error=str(e))
        await publish(task_id, {"status": "failed", "error": str(e)})
    finally:
        running_jobs.pop(task_id, None)


@router.get("/tasks")
def list_tasks():
    return {"tasks": [task.to_dict() for task in manager.list_tasks()]}


@router.post("/task/{task_id}/stop")
async def stop_task(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    job = running_jobs.get(task_id)
    if job and not job.done():
        job.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await job
    manager.update_task(task_id, status="stopped")
    await publish(task_id, {"status": "stopped"})
    return {"ok": True}


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")

    job = running_jobs.get(task_id)
    if job and not job.done():
        job.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await job

    for p in [Path(task.file_path), Path(task.output_path)]:
        if p.exists():
            p.unlink()

    deleted = manager.delete_task(task_id)
    subscribers.pop(task_id, None)
    event_buffers.pop(task_id, None)
    running_jobs.pop(task_id, None)
    return {"ok": deleted}


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

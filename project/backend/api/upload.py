from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile, HTTPException

from task.model import Task
from task.manager import TaskManager

router = APIRouter()
manager = TaskManager()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are allowed")
    task_id = str(uuid4())
    uploads = Path(__file__).resolve().parent.parent / "uploads"
    outputs = Path(__file__).resolve().parent.parent / "outputs"
    uploads.mkdir(exist_ok=True)
    outputs.mkdir(exist_ok=True)
    file_path = uploads / f"{task_id}_{file.filename}"
    output_path = outputs / f"{task_id}_result.xlsx"
    file_path.write_bytes(await file.read())

    task = Task(
        id=task_id,
        status="uploaded",
        progress=0.0,
        current_row=0,
        total_rows=0,
        file_path=str(file_path),
        output_path=str(output_path),
    )
    manager.create_task(task)
    return {"task_id": task_id}

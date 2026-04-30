from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import pandas as pd
import uuid
import os
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
JOBS_DIR = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
for d in (JOBS_DIR, UPLOADS_DIR, OUTPUTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Excel Address Parser Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def guess_address_columns(columns: List[str]) -> List[str]:
    keys = ["地址", "收货", "location", "address", "detail", "街道", "省", "市", "区"]
    scored = []
    for col in columns:
        score = sum(1 for k in keys if k.lower() in col.lower())
        if score > 0:
            scored.append((col, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]


def extract_customer_and_address(text: str) -> Dict[str, str]:
    text = (text or "").strip()
    phone_match = re.search(r"(?<!\d)(1[3-9]\d{9})(?!\d)", text)
    phone = phone_match.group(1) if phone_match else ""

    name = ""
    if phone:
        name_part = text.split(phone)[0].strip(" ,，;；:：")
        candidates = re.split(r"[ ,，;；:：\\/|]", name_part)
        candidates = [c for c in candidates if c]
        if candidates:
            name = candidates[-1][:20]

    address = text
    if name:
        address = address.replace(name, "", 1).strip(" ,，;；")
    if phone:
        address = address.replace(phone, "", 1).strip(" ,，;；")

    return {
        "raw": text,
        "customer_name": name,
        "phone": phone,
        "address": address,
    }


class ConfirmRequest(BaseModel):
    job_id: str
    target_column: str
    output_columns_prefix: str = "parsed"


@app.post("/api/upload")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are supported")

    job_id = str(uuid.uuid4())
    input_path = UPLOADS_DIR / f"{job_id}_{file.filename}"
    content = await file.read()
    input_path.write_bytes(content)

    df = pd.read_excel(input_path)
    columns = list(df.columns)
    suggestions = guess_address_columns(columns)

    job_state = {
        "job_id": job_id,
        "input_path": str(input_path),
        "output_path": "",
        "status": "awaiting_confirmation",
        "progress": 0,
        "columns": columns,
        "suggested_address_columns": suggestions,
        "target_column": "",
        "processed_rows": 0,
        "total_rows": len(df),
    }
    (JOBS_DIR / f"{job_id}.json").write_text(json.dumps(job_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return job_state


def load_job(job_id: str) -> Dict[str, Any]:
    p = JOBS_DIR / f"{job_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(p.read_text(encoding="utf-8"))


def save_job(job: Dict[str, Any]):
    (JOBS_DIR / f"{job['job_id']}.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    return load_job(job_id)


@app.post("/api/confirm")
def confirm_and_process(req: ConfirmRequest):
    job = load_job(req.job_id)
    df = pd.read_excel(job["input_path"])
    if req.target_column not in df.columns:
        raise HTTPException(status_code=400, detail="Target column not in Excel")

    job["status"] = "processing"
    job["target_column"] = req.target_column
    save_job(job)

    start = int(job.get("processed_rows", 0))
    total = len(df)
    for idx in range(start, total):
        val = str(df.at[idx, req.target_column]) if pd.notna(df.at[idx, req.target_column]) else ""
        parsed = extract_customer_and_address(val)
        df.at[idx, f"{req.output_columns_prefix}_customer_name"] = parsed["customer_name"]
        df.at[idx, f"{req.output_columns_prefix}_phone"] = parsed["phone"]
        df.at[idx, f"{req.output_columns_prefix}_address"] = parsed["address"]

        job["processed_rows"] = idx + 1
        job["progress"] = int((idx + 1) * 100 / max(total, 1))
        save_job(job)

    output_path = OUTPUTS_DIR / f"{req.job_id}_parsed.xlsx"
    df.to_excel(output_path, index=False)
    job["output_path"] = str(output_path)
    job["status"] = "completed"
    job["progress"] = 100
    save_job(job)

    return job


@app.get("/api/download/{job_id}")
def download_info(job_id: str):
    job = load_job(job_id)
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    return {"output_path": job["output_path"]}


if (BASE / "../frontend/dist").exists():
    app.mount("/", StaticFiles(directory=str(BASE / "../frontend/dist"), html=True), name="ui")

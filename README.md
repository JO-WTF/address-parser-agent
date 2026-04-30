# Excel Address Parser Agent

后端（FastAPI）+ 前端（Vue）实现：
- 上传 Excel，读取表头并猜测地址字段。
- 用户确认目标字段后，批量提取客户姓名/手机号/地址。
- 新字段回写 Excel。
- 任务进度保存到 job json，支持“断点继续”（同一 job 再次调用会从 processed_rows 继续）。

## Run

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend
直接打开 `frontend/index.html`（或用任意静态服务器）。

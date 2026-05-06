# Excel处理Agent系统

## 启动后端
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## 启动前端
```bash
cd frontend
npm install
npm run dev
```

## 示例Prompt
- 表头分析：`["客户信息", "收货地址", "电话"]`
- 提取：`张三 13800138000 北京市朝阳区望京SOHO`

## 示例测试数据
文件：`backend/sample_data.csv`
包含列：客户信息、收货地址、电话。

## API
- POST `/upload`
- GET `/headers/{task_id}`
- POST `/analyze`
- POST `/run`
- GET `/task/{task_id}`
- GET `/download/{task_id}`
- WS `/ws/task/{task_id}`

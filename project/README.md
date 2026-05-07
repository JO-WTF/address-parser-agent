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
npm run dev  # http://0.0.0.0:8099
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


## LLM配置
在 `backend/config.ini` 中配置：
- `base_url`
- `api_key`
- `model`

不再使用环境变量。


## 字段确认说明
LLM 分析阶段只猜测一个字段：`address_field`（详细地址列），用户只需要确认这一个字段。
后续逐行信息提取仅使用该字段文本作为 analyze 输入。


## 日志文件
后端所有日志（包括 Task 执行日志、WebSocket 发布日志、LLM 请求/响应日志）统一写入：`backend/logs/app.log`

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.upload import router as upload_router
from api.agent import router as agent_router
from api.task import router as task_router, subscribers
from storage.db import init_db

app = FastAPI(title="Excel Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(agent_router)
app.include_router(task_router)


@app.on_event("startup")
def startup():
    init_db()


@app.websocket("/ws/task/{task_id}")
async def ws_task(websocket: WebSocket, task_id: str):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    subscribers.setdefault(task_id, set()).add(q)
    print(f"[WS] connected task={task_id}, subscribers={len(subscribers.get(task_id, set()))}")
    try:
        while True:
            data = await q.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        subscribers.get(task_id, set()).discard(q)
        print(f"[WS] disconnected task={task_id}, subscribers={len(subscribers.get(task_id, set()))}")

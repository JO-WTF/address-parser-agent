from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.upload import router as upload_router
from api.agent import router as agent_router
from api.task import router as task_router, subscribers, event_buffers
from storage.db import init_db
from logger import get_logger, setup_logging

setup_logging()
logger = get_logger("main")

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
    subscribers.setdefault(task_id, set()).add(websocket)
    logger.info("[WS] connected task=%s, subscribers=%s", task_id, len(subscribers.get(task_id, set())))
    # send buffered events first in case client connected after task already started
    for event in event_buffers.get(task_id, []):
        await websocket.send_json(event)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        subscribers.get(task_id, set()).discard(websocket)
        logger.info("[WS] disconnected task=%s, subscribers=%s", task_id, len(subscribers.get(task_id, set())))

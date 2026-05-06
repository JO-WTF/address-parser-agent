from fastapi import APIRouter
from pydantic import BaseModel

from agent.core import Agent

router = APIRouter()
agent = Agent()


class AnalyzeRequest(BaseModel):
    headers: list[str]


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    return agent.analyze_headers(req.headers)

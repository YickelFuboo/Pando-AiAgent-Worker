"""Agent API 路由：查询支持的 Agent 类型等。"""
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.agents.core.base import AGENT_DIR


router = APIRouter(prefix="/agents")


class AgentTypesResponse(BaseModel):
    """支持的 Agent 类型列表"""
    agent_types: List[str] = Field(..., description="Agent 类型列表，来源于 .agent 目录下的子目录名称")


def _list_agent_types() -> List[str]:
    """从 .agent 目录下子目录名称得到 Agent 类型列表。"""
    if not AGENT_DIR.exists() or not AGENT_DIR.is_dir():
        return []
    return sorted(
        p.name for p in AGENT_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


@router.get(
    "/types",
    summary="查询支持的 Agent 类型",
    description="返回当前支持的 Agent 类型列表，来源于 .agent 目录下的子目录名称",
    response_model=AgentTypesResponse,
)
async def list_agent_types() -> AgentTypesResponse:
    """查询支持的 Agent 类型列表。"""
    return AgentTypesResponse(agent_types=_list_agent_types())

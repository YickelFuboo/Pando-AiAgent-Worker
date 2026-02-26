from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.agents.model import AgentType
from .models import Message


class SessionCreate(BaseModel):
    """会话创建"""
    agent_type: AgentType
    username: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    llm_name: Optional[str] = None

class SessionInfo(BaseModel):
    """会话信息"""
    session_id: str
    agent_type: AgentType
    username: str
    created_at: datetime
    last_updated: datetime
    description: Optional[str] = None    
    llm_name: Optional[str] = None  
    metadata: Optional[Dict[str, Any]] = None

class UserMessage(BaseModel):
    role: str
    content: str
    create_time: str

class SessionDetail(BaseModel):
    """会话详细信息"""
    session_id: str
    agent_type: AgentType
    llm_name: Optional[str] = None  
    messages: List[UserMessage]
    metadata: Optional[Dict[str, Any]] = None


from pydantic import BaseModel
from enum import Enum
from typing import Optional

class UserRequest(BaseModel):
    """用户请求"""
    session_id: str
    user_id: str
    user_question: str
    agent_type: str = "default"
    llm_provider: Optional[str] = ""
    llm_model: Optional[str] = ""

class UserResponse(BaseModel):
    """用户响应"""
    session_id: str
    content: str

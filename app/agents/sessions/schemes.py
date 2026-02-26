from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from .message import Message


class SessionCreate(BaseModel):
    """会话创建请求"""
    session_type: str = Field(..., description="会话类型")
    user_id: str = Field(..., description="用户ID")
    description: Optional[str] = Field(None, description="会话描述")
    metadata: Optional[Dict[str, Any]] = Field(None, description="会话元数据")
    llm_name: Optional[str] = Field(None, description="使用的模型名称")


class SessionInfo(BaseModel):
    """会话列表/概要信息"""
    session_id: str = Field(..., description="会话ID")
    session_type: str = Field(..., description="会话类型")
    user_id: str = Field(..., description="用户ID")
    created_at: datetime = Field(..., description="创建时间")
    last_updated: datetime = Field(..., description="最后更新时间")
    description: Optional[str] = Field(None, description="会话描述")
    llm_name: Optional[str] = Field(None, description="模型名称")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

    class Config:
        from_attributes = True


class UserMessage(BaseModel):
    """API 返回的单条消息(用户可读格式)"""
    role: str = Field(..., description="角色")
    content: str = Field(..., description="内容")
    create_time: str = Field(..., description="创建时间")


class SessionDetail(BaseModel):
    """会话详情(含消息列表)"""
    session_id: str = Field(..., description="会话ID")
    session_type: str = Field(..., description="会话类型")
    user_id: str = Field(..., description="用户ID")
    llm_name: Optional[str] = Field(None, description="模型名称")
    messages: List[UserMessage] = Field(default_factory=list, description="消息列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

    class Config:
        from_attributes = True

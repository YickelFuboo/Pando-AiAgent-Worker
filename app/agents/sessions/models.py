from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.infrastructure.database.models_base import Base


class SessionRecord(Base):
    """Agent 会话存储表：除 messages 外为独立列，messages 存 JSON。"""
    __tablename__ = "agent_sessions"

    session_id = Column(String(128), primary_key=True, comment="会话ID")
    description = Column(Text, nullable=True, comment="会话描述")
    agent_type = Column(String(64), nullable=False, comment="Agent 类型")
    channel_type = Column(String(64), nullable=False, server_default="", comment="渠道类型")
    user_id = Column(String(128), nullable=False, comment="用户ID")
    llm_provider = Column(String(128), nullable=False, server_default="", comment="模型提供者")
    llm_model = Column(String(128), nullable=False, server_default="default", comment="模型名称")
    metadata_ = Column("metadata", JSON, nullable=True, comment="元数据 JSON")
    messages = Column(JSON, nullable=False, comment="消息列表 JSON")
    last_consolidated = Column(Integer, nullable=False, server_default="0", comment="已合并消息数")

    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    last_updated = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="最后更新时间")

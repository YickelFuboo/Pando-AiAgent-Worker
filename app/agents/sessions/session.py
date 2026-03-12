from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .message import Message


class Session(BaseModel):
    """会话数据模型：仅负责会话元数据与消息列表，不包含压缩逻辑。"""

    session_id: str
    description: Optional[str] = None
    agent_type: str
    channel_type: str = ""
    user_id: str

    llm_provider: str
    llm_model: str = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # 会话历史信息
    messages: List[Message] = Field(default_factory=list)  # 历史会话记录
    last_consolidated: int = 0  # 已经合并到压缩结果的消息数量

    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def clear(self) -> None:
        """清空会话历史。"""
        self.messages.clear()
        self.last_consolidated = 0
        self.last_updated = datetime.now()
    
    def to_context(self, max_messages: int = 500) -> List[Dict[str, Any]]:
        """返回未合并到压缩结果的消息，按照用户回合对齐。"""
        unconsolidated = self.messages[self.last_consolidated:]
        sliced = unconsolidated[-max_messages:]
        return [s.to_context() for s in sliced]

    def to_information(self) -> Dict[str, Any]:
        """会话关键信息，供 API 列表等使用。"""
        return {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "description": self.description,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "metadata": self.metadata,
        }

    def model_dump(self) -> Dict[str, Any]:
        """序列化。"""
        return {
            "session_id": self.session_id,
            "description": self.description,
            "agent_type": self.agent_type,
            "channel_type": self.channel_type,
            "user_id": self.user_id,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "metadata": self.metadata,
            "messages": [msg.model_dump() for msg in self.messages],
            "last_consolidated": self.last_consolidated,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
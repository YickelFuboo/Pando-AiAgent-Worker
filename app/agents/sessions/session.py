from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from .message import Message


class Session(BaseModel):
    """会话数据模型：仅负责会话元数据与消息列表，不包含压缩逻辑。"""

    session_id: str
    description: Optional[str] = None
    session_type: str
    user_id: str

    llm_name: str = "default"
    messages: List[Message] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def model_dump(self) -> Dict[str, Any]:
        """序列化。"""
        return {
            "session_id": self.session_id,
            "description": self.description,
            "session_type": self.session_type,
            "user_id": self.user_id,
            "llm_name": self.llm_name,
            "messages": [msg.model_dump() for msg in self.messages],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    def add_message(self, message: Message) -> None:
        """追加一条消息，不执行压缩。需压缩时由调用方使用 context_compressor.get_context_for_llm。"""
        self.messages.append(message)
        self.last_updated = datetime.now()

    def get_history_for_context(self) -> List[Message]:
        """返回原始历史副本。若需按 token 压缩，请使用 context_compressor.get_context_for_llm(session, ...)。"""
        return self.messages.copy()

    def to_info_summary(self) -> Dict[str, Any]:
        """会话概要，供 API 列表等使用。"""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "description": self.description,
            "llm_name": self.llm_name,
            "metadata": self.metadata,
        }

    def to_info_detail(self) -> Dict[str, Any]:
        """会话详情，供 API 详情使用。"""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "user_id": self.user_id,
            "llm_name": self.llm_name,
            "messages": [msg.to_user_message() for msg in self.messages],
            "metadata": self.metadata,
        }

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

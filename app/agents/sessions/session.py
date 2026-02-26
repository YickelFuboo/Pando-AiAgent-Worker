from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .message import Message


class Session(BaseModel):
    """会话数据模型：仅负责会话元数据与消息列表，不包含压缩逻辑。"""

    session_id: str
    description: Optional[str] = None
    session_type: str
    user_id: str

    llm_provider: str
    llm_name: str = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # 会话历史信息
    messages: List[Message] = Field(default_factory=list)  # 历史会话记录
    last_consolidated: int = 0  # 已经合并到压缩结果的消息数量
    memory: str = ""  # 当前会话记忆，Markdown 文档字符串

    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    def model_dump(self) -> Dict[str, Any]:
        """序列化。"""
        return {
            "session_id": self.session_id,
            "description": self.description,
            "session_type": self.session_type,
            "user_id": self.user_id,
            "llm_provider": self.llm_provider,
            "llm_name": self.llm_name,
            "metadata": self.metadata,
            "messages": [msg.model_dump() for msg in self.messages],
            "last_consolidated": self.last_consolidated,
            "memory": self.memory,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    def add_message(self, message: Message) -> None:
        """追加一条消息，不执行压缩。需压缩时由调用方使用 context_compressor.get_context_for_llm。"""
        self.messages.append(message)
        self.last_updated = datetime.now()

    def get_history_for_context(self, max_messages: int = 500) -> List[Dict[str, Any]]:
        """返回未合并到压缩结果的消息，按照用户回合对齐。"""
        unconsolidated = self.messages[self.last_consolidated:]
        sliced = unconsolidated[-max_messages:]

        # 丢弃前面的非用户消息，避免孤立的 tool_result 块
        #for i, m in enumerate[Message](sliced):
        #    if m.get("role") == "user":
        #        sliced = sliced[i:]
        #        break

        return [s.model_dump() for s in sliced]        

    def clear(self) -> None:
        """清空会话历史。"""
        self.messages.clear()
        self.last_consolidated = 0
        self.memory = ""
        self.last_updated = datetime.now()

    def to_information(self) -> Dict[str, Any]:
        """会话关键信息，供 API 列表等使用。"""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "description": self.description,
            "llm_provider": self.llm_provider,
            "llm_name": self.llm_name,
            "metadata": self.metadata,
        }

    def set_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

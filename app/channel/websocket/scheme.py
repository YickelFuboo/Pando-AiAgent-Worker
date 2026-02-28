from enum import Enum
from typing import Optional

class WebSocketMessageType(Enum):
    """消息类型"""
    # 连接成功
    CONNECT_SUCCESS = "connect_success"
    # 连接失败
    CONNECT_ERROR = "connect_error"
    # 断开连接
    DISCONNECT = "disconnect"
    # 处理通知
    RESPONSE = "response"

class WebSocketMessage:
    """websocket消息"""
    message_type: WebSocketMessageType
    current_session_id: str
    parent_session_id: Optional[str] = None
    content: str

    def __init__(self, message_type: WebSocketMessageType, current_session_id: str, content: str, parent_session_id: Optional[str] = None):
        self.message_type = message_type
        self.current_session_id = current_session_id
        self.parent_session_id = parent_session_id
        self.content = content
    
    def to_dict(self):
        return {
            "message_type": self.message_type.value,
            "current_session_id": self.current_session_id,
            "parent_session_id": self.parent_session_id,
            "content": self.content
        }

import json
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import re


class Role(str, Enum):
    """消息角色"""    
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Function(BaseModel):
    name: str
    arguments: str

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化方法"""

        # 确保 arguments 是字符串格式
        arguments = self.arguments
        if isinstance(arguments, (dict, list)):
            arguments = json.dumps(arguments)
        elif isinstance(arguments, str):
            # 如果已经是字符串，尝试解析并重新序列化以确保格式正确
            try:
                arguments = json.dumps(json.loads(arguments), ensure_ascii=False)
            except json.JSONDecodeError:
                # 如果不是有效的 JSON 字符串，直接序列化
                arguments = json.dumps(arguments, ensure_ascii=False)

        return {
            "name": self.name,
            "arguments": arguments
        }


class ToolCall(BaseModel):
    """Represents a tool/function call in a message"""
    id: str
    type: str = "function"
    function: Function

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化方法"""
        return {
            "id": self.id,
            "type": self.type,
            "function": self.function.model_dump()
        }


class Message(BaseModel):
    """聊天消息基础结构"""
    role: Role
    content: str

    # 模型返回的工具调用信息记录
    tool_calls: Optional[List[ToolCall]] = Field(default=None)
    # 工具执行结果信息
    name: Optional[str] = Field(default=None)
    tool_call_id: Optional[str] = Field(default=None)

    # 添加创建时间
    create_time: Optional[datetime] = Field(default=None)

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化方法"""
        message = {"role": self.role.value}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls is not None:
            message["tool_calls"] = [tool_call.model_dump() for tool_call in self.tool_calls]
        if self.name is not None and self.tool_call_id is not None:
            message["name"] = self.name
            message["tool_call_id"] = self.tool_call_id
        if self.create_time:
            message["create_time"] = self.create_time.strftime("%Y-%m-%d %H:%M:%S")
        return message
    
    def to_json(self) -> str:
        """将消息转换为JSON字符串"""
        return json.dumps(self.model_dump(), ensure_ascii=False)

    def to_user_message(self) -> Dict[str, Any]:
        """将消息转换易于用户阅读的消息格式"""
        message = {'role': self.role.value}

        # 添加内容
        content = ""
        if self.tool_calls:
            if self.content:
                content = self.content
                content += "\n\n"
            # 添加toolcall信息
            content += "## 执行工具\n"
            for index, tool_call in enumerate(self.tool_calls):
                content += f"### {index+1}. {tool_call.function.name}\n"
                content += "参数：\n"
                # 将参数转换为格式化的 JSON
                args_dict = json.loads(tool_call.function.arguments)
                formatted_json = json.dumps(args_dict, ensure_ascii=False, indent=2)
                content += f"```json\n{formatted_json}\n```\n\n"
        elif self.name and self.tool_call_id:
            # 尝试检测并格式化JSON内容
            #try:
                # 尝试解析内容是否为JSON
                #json_content = json.loads(self.content)
                # 如果是JSON，则格式化显示
                #formatted_json = json.dumps(json_content, ensure_ascii=False, indent=2)
                #content = f"### 工具{self.name}执行结果：\n\n{formatted_json}\n"
            #except json.JSONDecodeError:
                # 如果不是JSON，则按原样显示
            content = f"### 工具{self.name}执行结果：\n\n{self.content}"
        else:
            content = self.content

        message['content'] = content

        # 添加创建时间
        if self.create_time:
            message['create_time'] = self.create_time.strftime("%Y-%m-%d %H:%M:%S")

        return message

    @classmethod
    def system_message(cls, content: str) -> "Message":
        """创建系统消息"""
        return cls(role="system", content=content)
    
    @classmethod
    def user_message(cls, content: str) -> "Message":
        """创建用户消息"""
        return cls(role="user", content=content, create_time=datetime.now())

    @classmethod
    def assistant_message(cls, content: Optional[str] = None) -> "Message":
        """创建助手消息"""
        return cls(role="assistant", content=content, create_time=datetime.now())

    @classmethod
    def from_tool_calls(cls, content: Union[str, List[str]] = "", tool_calls: Optional[List[ToolCall]] = None, **kwargs):
        """Create ToolCallsMessage from raw tool calls.

        Args:
            tool_calls: Raw tool calls from LLM
            content: Optional message content
        """
        formatted_calls = [
            {"id": call.id, "function": call.function.model_dump(), "type": "function"}
            for call in tool_calls
        ]
        return cls(
            role="assistant", content=content, tool_calls=formatted_calls, create_time=datetime.now(), **kwargs
        )
    
    @classmethod
    def tool_message(cls, content: str, name: str, tool_call_id: str) -> "Message":
        """Create a tool message"""
        return cls(role="tool", content=content, name=name, tool_call_id=tool_call_id, create_time=datetime.now())
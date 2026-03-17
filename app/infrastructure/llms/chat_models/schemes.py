from typing import Any,Dict,List,Optional
from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens:int=0
    output_tokens:int=0
    cache_read_tokens:int=0
    cache_write_tokens:int=0
    total_tokens:int=0
    reasoning_tokens:int=0
    tool_tokens:int=0
    other_tokens:int=0

    def overflow_basis(self)->int:
        tokens=(self.input_tokens or 0)+(self.cache_read_tokens or 0)+(self.cache_write_tokens or 0)
        if tokens>0:
            return tokens
        return self.total_tokens or 0

    def add(self,other:"TokenUsage")->"TokenUsage":
        if other is None:
            return self
        self.input_tokens+=(other.input_tokens or 0)
        self.output_tokens+=(other.output_tokens or 0)
        self.cache_read_tokens+=(other.cache_read_tokens or 0)
        self.cache_write_tokens+=(other.cache_write_tokens or 0)
        self.total_tokens+=(other.total_tokens or 0)
        self.reasoning_tokens+=(other.reasoning_tokens or 0)
        self.tool_tokens+=(other.tool_tokens or 0)
        self.other_tokens+=(other.other_tokens or 0)
        return self


class ModelLimits(BaseModel):
    context_limit:Optional[int]=None
    max_output_tokens:Optional[int]=None
    max_input_tokens:Optional[int]=None


class ChatResponse(BaseModel):   
    """聊天响应格式"""
    success: bool = True         # 返回申请情况下成功与否
    content: str                 # 返回内容，包含成功情况下正确内容和失败情况下错误信息


class ToolInfo(BaseModel):
    """工具调用信息"""
    id: str
    name: str
    args: Dict[str, Any]


class AskToolResponse(BaseModel):
    """工具调用响应格式"""
    success: bool = True         # 返回申请情况下成功与否
    content: Optional[str] = None                 # 返回内容，包含成功情况下思考内容和失败情况下错误信息
    tool_calls: Optional[List[ToolInfo]] = None  # 支持多个工具调用


class LLMInfo(BaseModel):
    """LLM信息模型"""
    name: str
    type: str
    description: str
    max_tokens: int
    api_style: str


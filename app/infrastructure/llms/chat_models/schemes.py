import json
from typing import Any,Dict,List,Optional
import json_repair
from pydantic import BaseModel,field_validator


def parse_tool_args(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if v is None:
        return {}
    if not isinstance(v, str):
        return {}
    s = v.strip()
    if not s:
        return {}
    if s.startswith("```"):
        lines=[ln for ln in s.splitlines() if not ln.strip().startswith("```")]
        s="\n".join(lines).strip()
    if len(s)>=2 and s[0]==s[-1] and s[0] in ("'",'"'):
        s=s[1:-1].strip()

    
    try:
        o=json.loads(s)
        if isinstance(o, dict):
            return o
        if isinstance(o, str):
            try:
                o2=json.loads(o)
                if isinstance(o2, dict):
                    return o2
            except json.JSONDecodeError:
                pass
    except json.JSONDecodeError:
        pass
    try:
        o=json_repair.loads(s)
        if isinstance(o, dict):
            return o
        if isinstance(o, str):
            try:
                o2=json_repair.loads(o)
                if isinstance(o2, dict):
                    return o2
            except Exception:
                pass
    except Exception:
        pass

    def _iter_json_object_snippets(text: str):
        i=0
        n=len(text)
        while i<n:
            if text[i]!="{":
                i+=1
                continue
            start=i
            depth=0
            in_str=False
            esc=False
            j=i
            while j<n:
                ch=text[j]
                if in_str:
                    if esc:
                        esc=False
                    elif ch=="\\":
                        esc=True
                    elif ch=='"':
                        in_str=False
                else:
                    if ch=='"':
                        in_str=True
                    elif ch=="{":
                        depth+=1
                    elif ch=="}":
                        depth-=1
                        if depth==0:
                            yield text[start:j+1]
                            i=j+1
                            break
                j+=1
            else:
                break
    for snippet in _iter_json_object_snippets(s):
        try:
            o=json.loads(snippet)
            if isinstance(o, dict):
                return o
        except json.JSONDecodeError:
            pass
        try:
            o=json_repair.loads(snippet)
            if isinstance(o, dict):
                return o
        except Exception:
            pass
    return {}


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

    @field_validator("args", mode="before")
    @classmethod
    def _args_must_be_dict(cls, v: Any) -> Dict[str, Any]:
        return parse_tool_args(v)


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


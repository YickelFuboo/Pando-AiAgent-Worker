import json
import re
from typing import Any,Dict,List,Optional
import json_repair
from pydantic import BaseModel,field_validator


class ToolArgsParser:
    @staticmethod
    def parse(v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        if v is None:
            return {}
        if not isinstance(v, str):
            return {}
        s=v.strip()
        if not s:
            return {}
        
        s=ToolArgsParser._strip_code_fence(s) # 去除代码块
        s=ToolArgsParser._strip_outer_quotes(s) # 去除外层引号
        out=ToolArgsParser._try_json_then_double(s) # 尝试解析为JSON
        if out is not None:
            return out
        
        out=ToolArgsParser._try_repair_then_double(s) # 尝试修复并解析为JSON    
        if out is not None:
            return out
        
        for snippet in ToolArgsParser._iter_json_object_snippets(s): # 迭代JSON对象片段
            out=ToolArgsParser._try_json_then_double(snippet) # 尝试解析为JSON
            if out is not None:
                return out
            out=ToolArgsParser._try_repair_then_double(snippet) # 尝试修复并解析为JSON
            if out is not None:
                return out
        out=ToolArgsParser._try_repair_greedy_object(s) # 尝试修复贪婪对象  
        if out is not None:
            return out
        out=ToolArgsParser._extract_path_content(s)
        if out is not None:
            return out
        return {}

    @staticmethod
    def _strip_code_fence(s: str) -> str:
        # 去除代码块
        if not s.startswith("```"):
            return s
        lines=[ln for ln in s.splitlines() if not ln.strip().startswith("```")]
        return "\n".join(lines).strip()

    @staticmethod
    def _strip_outer_quotes(s: str) -> str:
        # 去除外层引号
        if len(s)<2:
            return s
        if s[0]==s[-1] and s[0] in ("'",'"'):
            return s[1:-1].strip()
        return s

    @staticmethod
    def _try_json_then_double(s: str) -> Optional[Dict[str, Any]]:
        # 尝试解析为JSON
        try:
            o=json.loads(s)
        except json.JSONDecodeError:
            return None
        if isinstance(o, dict):
            return o
        if isinstance(o, str):
            try:
                o2=json.loads(o)
            except json.JSONDecodeError:
                return None
            return o2 if isinstance(o2, dict) else None
        return None

    @staticmethod
    def _try_repair_then_double(s: str) -> Optional[Dict[str, Any]]:
        # 尝试修复并解析为JSON
        try:
            o=json_repair.loads(s)
        except Exception:
            return None
        if isinstance(o, dict):
            return o
        if isinstance(o, str):
            try:
                o2=json_repair.loads(o)
            except Exception:
                return None
            return o2 if isinstance(o2, dict) else None
        return None

    @staticmethod
    def _iter_json_object_snippets(text: str):
        # 目标:从一段“混杂文本”中提取所有“完整闭合”的JSON对象片段,逐个yield出形如"{...}"的子串
        #
        # 为什么需要它:
        # - 模型返回的arguments经常不是纯JSON,可能前后夹杂日志/解释文字/markdown代码块
        # - 直接用find("{")+rfind("}")会贪婪吞掉多个对象/无关内容,导致解析失败或误解析
        #
        # 核心思想:
        # - 从左到右扫描,遇到'{'认为可能是对象起点
        # - 用depth统计大括号嵌套层级:'{'=>+1,'}'=>-1
        # - 当depth从1回到0时,说明从start到当前位置j形成了一个“括号配平”的对象片段,即可yield
        #
        # 关键细节(避免把字符串内容里的括号当结构括号):
        # - in_str:是否处于JSON字符串字面量内部(双引号包裹)
        # - esc:处理反斜杠转义,避免把\"误当作字符串结束
        # - 只有在in_str==False时,才对'{'/'}'做depth计数
        #
        # 注意:
        # - 该方法不验证片段一定是合法JSON(比如字段里引号坏了也可能配平),只负责“结构上闭合”
        # - 外层会对yield出的片段再用json.loads/json_repair.loads尝试解析成dict
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

    @staticmethod
    def _try_repair_greedy_object(s: str) -> Optional[Dict[str, Any]]:
        # 尝试修复贪婪对象
        start=s.find("{")
        end=s.rfind("}")
        if start==-1 or end==-1 or end<=start:
            return None
        snippet=s[start:end+1]
        try:
            o=json_repair.loads(snippet)
        except Exception:
            return None
        return o if isinstance(o, dict) else None

    @staticmethod
    def _extract_path_content(s: str) -> Optional[Dict[str, Any]]:
        # 提取路径和内容
        m_path=re.search(r'"path"\s*:\s*"((?:\\.|[^"\\])*)"',s)
        m_content=re.search(r'"content"\s*:\s*"((?:\\.|[^"\\])*)"',s,re.DOTALL)
        if not (m_path or m_content):
            return None
        out={}
        if m_path:
            out["path"]=ToolArgsParser._unescape_json_string(m_path.group(1))
        if m_content:
            out["content"]=ToolArgsParser._unescape_json_string(m_content.group(1))
        return out

    @staticmethod
    def _unescape_json_string(raw: str) -> str:
        # 反义JSON字符串
        try:
            return json.loads('"'+raw+'"')
        except Exception:
            return raw


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
        return ToolArgsParser.parse(v)


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


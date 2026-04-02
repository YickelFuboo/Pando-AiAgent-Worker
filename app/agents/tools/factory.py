import json
import logging
from typing import Any,Dict,List,Optional
from .base import BaseTool
from .schemes import ToolResult,ToolSuccessResult,ToolErrorResult,ToolResultStatus
from .truncation import Truncate
from app.agents.tools.local.ask_question import AskQuestion
from app.agents.tools.local.batch_tool import BatchTool
from app.agents.tools.local.code.apply_patch import ApplyPatchTool
from app.agents.tools.local.code.code_search import CodeDependenciesSearchTool,CodeRelatedFilesSearchTool,CodeSimilarSearchTool
from app.agents.tools.local.code.code_shell import CodeShellTool
from app.agents.tools.local.code.list_code_files import ListCodeFilesTool
from app.agents.tools.local.code.lsp_tool import LspTool
from app.agents.tools.local.cron import CronTool
from app.agents.tools.local.dir_read import ReadDirTool
from app.agents.tools.local.file_read import ReadFileTool
from app.agents.tools.local.file_search import GlobTool,GrepTool
from app.agents.tools.local.file_write import InsertFileTool,MultiReplaceTextTool,ReplaceFileTextTool,WriteFileTool
from app.agents.tools.local.shell import ExecTool
from app.agents.tools.local.spawn import SpawnTool
from app.agents.tools.local.todo import TodoReadTool,TodoWriteTool
from app.agents.tools.local.web import WebFetchTool,WebSearchTool


def register_tools_by_config(
    *,
    config_json:Dict[str,Any],
    tools_factory:"ToolsFactory",
    agent_type:str,
    session_id:str,
    user_id:str,
    channel_id:str,
    channel_type:str,
    subagent_manager:Optional[Any]=None,
    params:Dict[str,Any],
)->None:
    # 解析配置文件中的工具权限
    usable=set()
    tools_policy=config_json.get("tools")
    if isinstance(tools_policy,dict):
        for tool_name,decision in tools_policy.items():
            if str(decision).strip().lower()=="allow":
                usable.add(str(tool_name))

    # 根据 agent_type 和 params 初始化工具参数
    is_code_agent=agent_type in {"CodeAnalysis","CodeAgent","CodingAgent"}
    repo_id=str(params.get("repo_id") or "").strip() if is_code_agent else ""
    tool_init_kwargs={"repo_id":repo_id,"isCodeAgent":is_code_agent}
    tools_to_register:List[BaseTool]=[]

    # 注册工具
    if "ask_question" in usable:
        tools_to_register.append(AskQuestion())
    if "read_file" in usable:
        tools_to_register.append(ReadFileTool(**tool_init_kwargs))
    if "write_file" in usable:
        tools_to_register.append(WriteFileTool(**tool_init_kwargs))
    if "replace_file_text" in usable:
        tools_to_register.append(ReplaceFileTextTool(**tool_init_kwargs))
    if "insert_file" in usable:
        tools_to_register.append(InsertFileTool(**tool_init_kwargs))
    if "multi_replace_text" in usable:
        tools_to_register.append(MultiReplaceTextTool(**tool_init_kwargs))
    if "glob_search" in usable:
        tools_to_register.append(GlobTool())
    if "grep_search" in usable:
        tools_to_register.append(GrepTool())
    if "read_dir" in usable:
        tools_to_register.append(ReadDirTool())
    if "exec" in usable:
        tools_to_register.append(ExecTool())

    if "list_code_files" in usable:
        tools_to_register.append(ListCodeFilesTool())
    if "apply_patch" in usable:
        tools_to_register.append(ApplyPatchTool(repo_id=repo_id))
    if "code_similar_search" in usable:
        tools_to_register.append(CodeSimilarSearchTool(repo_id=str(params.get("repo_id") or "")))
    if "code_related_files_search" in usable:
        tools_to_register.append(CodeRelatedFilesSearchTool(repo_id=str(params.get("repo_id") or "")))
    if "code_dependencies_search" in usable:
        tools_to_register.append(CodeDependenciesSearchTool(repo_id=str(params.get("repo_id") or "")))
    if "lsp" in usable:
        tools_to_register.append(LspTool(repo_id=repo_id))
    if "code_shell" in usable:
        tools_to_register.append(CodeShellTool())

    if "todo_read" in usable:
        tools_to_register.append(TodoReadTool(session_id=session_id))
    if "todo_write" in usable:
        tools_to_register.append(TodoWriteTool(session_id=session_id))
    if "batch_tools" in usable:
        tools_to_register.append(BatchTool(tools_factory=tools_factory))
    if "web_search" in usable:
        tools_to_register.append(WebSearchTool())
    if "web_fetch" in usable:
        tools_to_register.append(WebFetchTool())
    if "cron" in usable:
        tools_to_register.append(CronTool(session_id=session_id,user_id=user_id,agent_type=agent_type,channel_id=channel_id,channel_type=channel_type))
    if "spawn" in usable and subagent_manager is not None:
        tools_to_register.append(SpawnTool(subagent_manager))
    if tools_to_register:
        tools_factory.register_tools(*tools_to_register)


TOOLS_CACHE_NAME = ("exec",)
MAX_CACHE_SIZE = 256
DELEGATION_TOOL_NAME = "spawn"


def _cache_key(tool_name: str, tool_params: Dict[str, Any]) -> tuple[str, str]:
    """工具名 + 参数生成可哈希的缓存键（参数按 key 排序序列化）。"""
    return (tool_name, json.dumps(tool_params, sort_keys=True))


class ToolsFactory:
    """工具市场管理器；超长输出截断时的 hint 根据是否可委托子 Agent（当前是否注册 spawn）选择不同提示。"""
    def __init__(self, *tools: BaseTool, agent_workspace: str = ""):
        self._tools: Dict[str, BaseTool] = {tool.name: tool for tool in tools}
        self._cacheable: set[str] = set(TOOLS_CACHE_NAME)
        self._max_cache_size = MAX_CACHE_SIZE
        self._result_cache: Dict[tuple[str, str], ToolResult] = {}
        self._agent_workspace = agent_workspace

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def has_spawn_tool(self) -> bool:
        """当前是否可委托子 Agent：由工具集合是否含 spawn 决定。"""
        return self.has_tool(DELEGATION_TOOL_NAME)

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def register_tools(self, *tools: BaseTool) -> None:
        for tool in tools:
            self.register_tool(tool)

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name)

    def to_params(self) -> List[Dict[str, Any]]:
        return [tool.to_param() for tool in self._tools.values()]

    def _build_fix_hint(self, *, tool_name: str, reason: str, missing: List[str] = None, errors: List[str] = None) -> str:
        payload = {
            "error": "tool_call_failed",
            "tool": tool_name,
            "missing": missing or [],
            "errors": errors or [],
            "guidance": [
                "please try again. ensure the function.arguments is a valid."
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    async def execute(self, tool_name: str, tool_params: Dict[str, Any]) -> ToolResult:
        """执行工具调用"""
        try:
            tool = self.get_tool(tool_name)
            if not tool:
                return ToolErrorResult(f"Tool {tool_name} not found")

            # 获取参数解析诊断字段
            args_error=tool_params.get("__args_error__") or None
            if args_error:
                msg=self._build_fix_hint(
                    tool_name=tool_name,
                    reason="the tool args from llm is invalid.",
                    missing=[],
                    errors=[args_error],
                )
                return ToolErrorResult(msg)

            # 过滤解析诊断字段，避免影响真实工具执行
            clean_params={k:v for k,v in tool_params.items() if not k.startswith("__args_error__")}
            tool_params=clean_params

            # 检查参数是否有缺失
            required = set(tool.parameters.get("required", []) or [])
            provided = set(tool_params.keys())
            missing = required - provided
            if missing:
                msg = self._build_fix_hint(
                    tool_name=tool_name,
                    reason="the tool args from llm is missing required parameters.",
                    missing=sorted(list(missing)),
                    errors=["missing required parameters."],
                )
                return ToolErrorResult(msg)

            # 检查参数是否合法
            if hasattr(tool, "validate_params"):
                try:
                    errors = tool.validate_params(tool_params)  # type: ignore[attr-defined]
                except Exception as e:
                    msg = self._build_fix_hint(
                        tool_name=tool_name, 
                        reason="the tool call failed.", 
                        errors=[f"the tool call failed. reason: {e}"]
                    )
                    return ToolErrorResult(msg)
                if errors:
                    msg = self._build_fix_hint(
                        tool_name=tool_name, 
                        reason="the tool call failed.", 
                        errors=errors
                    )
                    return ToolErrorResult(msg)

            # 可缓存工具：先查缓存
            if tool_name in self._cacheable:
                key = _cache_key(tool_name, tool_params)
                if key in self._result_cache:
                    logging.info("execute_tool: %s (cache hit)", tool_name)
                    return self._result_cache[key]

            # 执行工具调用
            result = await tool.execute(**tool_params)

            # 仅对成功结果做超长截断，统一在 Factory 处理；工具无需自行截断
            if result.status == ToolResultStatus.EXECUTE_SUCCESS and self._agent_workspace:
                raw = f"{result.result}"
                truncated = Truncate.output(
                    raw,
                    self._agent_workspace,
                    has_task_tool=self.has_spawn_tool,
                )
                if truncated.truncated and truncated.output_path:
                    result = ToolSuccessResult(
                        truncated.content,
                        metadata={"truncated": True, "outputPath": truncated.output_path},
                    )

            # 可缓存工具：写入缓存并限制容量
            if tool_name in self._cacheable:
                key = _cache_key(tool_name, tool_params)
                if self._max_cache_size and len(self._result_cache) >= self._max_cache_size:
                    oldest = next(iter(self._result_cache))
                    del self._result_cache[oldest]
                self._result_cache[key] = result

            return result

        except Exception as e:
            logging.error(f"Tool({tool_name}) execution error: {str(e)}")
            return ToolErrorResult(f"Tool execution error: {str(e)}") 
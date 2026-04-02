import json
import logging
from typing import Any,Dict,List
from .base import BaseTool
from .schemes import ToolResult,ToolSuccessResult,ToolErrorResult,ToolResultStatus
from .truncation import Truncate

TOOLS_CACHE_NAME = ("exec",)
MAX_CACHE_SIZE = 256
DELEGATION_TOOL_NAME = "spawn"


def _cache_key(tool_name: str, tool_params: Dict[str, Any]) -> tuple[str, str]:
    """工具名 + 参数生成可哈希的缓存键（参数按 key 排序序列化）。"""
    return (tool_name, json.dumps(tool_params, sort_keys=True))


class ToolsFactory:
    """工具市场管理器；超长输出截断时的 hint 根据是否可委托子 Agent（当前是否注册 spawn）选择不同提示。"""
    def __init__(self, *tools: BaseTool, workspace_path: str = ""):
        self._tools: Dict[str, BaseTool] = {tool.name: tool for tool in tools}
        self._cacheable: set[str] = set(TOOLS_CACHE_NAME)
        self._max_cache_size = MAX_CACHE_SIZE
        self._result_cache: Dict[tuple[str, str], ToolResult] = {}
        self.workspace_path = workspace_path

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
            if result.status == ToolResultStatus.EXECUTE_SUCCESS and self.workspace_path:
                raw = f"{result.result}"
                truncated = Truncate.output(
                    raw,
                    self.workspace_path,
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
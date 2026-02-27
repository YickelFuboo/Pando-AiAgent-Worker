from typing import Dict, List, Tuple, Any
from app.logger import logger
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolTimeoutResult, ToolErrorResult, ToolCancelledResult


class ToolsFactory:
    """工具市场管理器"""
    def __init__(self, *tools: BaseTool):
        self._tools: Dict[str, BaseTool] = {tool.name: tool for tool in tools}

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def register_tool(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def register_tools(self, *tools: BaseTool) -> None:
        for tool in tools:
            self.register_tool(tool)

    def unregister_tool(self, name: str) -> None:
        self._tools.pop(name)

    def to_params(self) -> List[Dict[str, Any]]:
        return [tool.to_param() for tool in self._tools.values()]

    async def execute(self, tool_name: str, tool_params: Dict[str, Any]) -> ToolResult:
        """执行工具调用"""
        try:
            logger.info(f"execute_tool: {tool_name}, params: {tool_params}")

            tool = self.get_tool(tool_name)
            if not tool:
                return ToolErrorResult(f"Tool {tool_name} not found")

            # 检查参数是否有缺失
            required = set(tool.parameters.get("required", []) or [])
            provided = set(tool_params.keys())
            missing = required - provided
            if missing:
                msg = f"Missing required parameters: {', '.join(sorted(missing))}"
                logger.error(msg)
                return ToolErrorResult(msg)

            # 检查参数是否合法
            if hasattr(tool, "validate_params"):
                try:
                    errors = tool.validate_params(tool_params)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.error("Tool(%s) schema validation error: %s", tool_name, e)
                    return ToolErrorResult(f"Tool parameter schema error: {e}")
                if errors:
                    msg = "Invalid parameters: " + "; ".join(errors)
                    logger.error("Tool(%s) %s", tool_name, msg)
                    return ToolErrorResult(msg)

            # 执行工具调用
            return await tool.execute(**tool_params)
                
        except Exception as e:
            logger.error(f"Tool({tool_name}) execution error: {str(e)}")
            return ToolErrorResult(f"Tool execution error: {str(e)}") 
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

    def add_tool(self, tool: BaseTool):
        self._tools[tool.name] = tool
        return self
    def add_tools(self, *tools: BaseTool):
        for tool in tools:
            self.add_tool(tool)
        return self
    def remove_tool(self, name: str):
        self._tools.pop(name)
        return self
    def to_params(self) -> List[Dict[str, Any]]:
        return [tool.to_param() for tool in self._tools.values()]

    async def execute_tool(self, tool_name: str, tool_params: Dict[str, Any]) -> ToolResult:
        """执行工具调用"""
        try:
            logger.info(f"execute_tool: {tool_name}, params: {tool_params}")

            tool = self.get_tool(tool_name)
            if not tool:
                return ToolErrorResult(f"Tool {tool_name} not found")
            
            # 验证必需参数是否存在
            required_params = set(tool.parameters.get('properties', {}).keys())
            provided_params = set(tool_params.keys())   
            missing_params = required_params - provided_params
            
            if missing_params:
                logger.error(f"Missing required parameters: {', '.join(missing_params)}")
                return ToolErrorResult(f"Missing required parameters: {', '.join(missing_params)}")
            
            # 执行工具调用
            return await tool.execute(**tool_params)
                
        except Exception as e:
            logger.error(f"Tool({tool_name}) execution error: {str(e)}")
            return ToolErrorResult(f"Tool execution error: {str(e)}") 
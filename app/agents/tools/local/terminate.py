from typing import Dict
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult


class Terminate(BaseTool):
    """终止工具"""
    @property
    def name(self) -> str:
        return "terminate"
        
    @property
    def description(self) -> str:
        return """When you consider the task complete, or need to terminate the current task, you should use this tool."""
    
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",   
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "The summary of the task completion. It should be a brief description of the task completion process, the results or conclusions of the task.",
                }
            },
            "required": ["summary"]
        }      
    
    async def execute(self, summary: str, **kwargs) -> str:
        """Finish the current execution"""
        return ToolSuccessResult(f"The task has been completed with summary: {summary}")
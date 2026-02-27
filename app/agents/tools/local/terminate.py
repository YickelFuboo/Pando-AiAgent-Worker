from typing import Dict, Any
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolTimeoutResult, ToolErrorResult, ToolCancelledResult


class Terminate(BaseTool):
    """Terminate the current task."""
    @property
    def name(self) -> str:
        return "terminate"
        
    @property
    def description(self) -> str:
        return "When you think the task is complete or you need to terminate the current task, you should use this tool."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",   
            "properties": {
                "status": {
                    "type": "string",
                    "description": "The reason for terminating the task.",
                    "enum": ["success", "failure"],
                }
            },
            "required": ["status"]
        }      
    
    async def execute(self, reason: str, **kwargs) -> ToolResult:
        """Finish the current execution"""
        return ToolSuccessResult(f"The task has been completed with status: {reason}")
from typing import Dict
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolTimeoutResult, ToolErrorResult, ToolCancelledResult


class Terminate(BaseTool):
    """终止工具"""
    @property
    def name(self) -> str:
        return "terminate"
        
    @property
    def description(self) -> str:
        return """当您认为任务已经完成，或者需要终止当前任务时，应使用此工具。"""
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",   
            "properties": {
                "status": {
                    "type": "string",
                    "description": "终止任务的原因",
                    "enum": ["success", "failure"],
                }
            },
            "required": ["status"]
        }      
    
    async def execute(self, reason: str, **kwargs) -> str:
        """Finish the current execution"""
        return ToolSuccessResult(f"The task has been completed with status: {reason}")
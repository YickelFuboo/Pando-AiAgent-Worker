from typing import Dict, Any
from enum import Enum


class ToolResultStatus(Enum):
    """工具执行结果状态枚举"""
    TOOL_NOT_FOUND = "tool_not_found"  # 工具不存在
    EXECUTE_SUCCESS = "execute_success"  # 执行成功
    EXECUTE_TIMEOUT = "execute_timeout" # 执行超时
    EXECUTE_ERROR = "execute_error" # 执行错误
    EXECUTE_CANCELLED = "execute_cancelled" # 执行取消
    EXECUTE_ABORTED = "execute_aborted" # 执行中止
    EXECUTE_INTERRUPTED = "execute_interrupted" # 执行中断
    EXECUTE_PAUSED = "execute_paused" # 执行暂停
    EXECUTE_RESUMED = "execute_resumed" # 执行恢复


class ToolResult:
    """工具执行结果"""
    def __init__(self, status: ToolResultStatus, result: Any):
        self.status = status
        self.result = result

    def __bool__(self):
        """判断工具执行结果是否成功"""
        return self.status == ToolResultStatus.EXECUTE_SUCCESS

    def to_json(self) -> Dict:  
        """Convert tool result to JSON format."""
        return {
            "status": self.status.value,
            "result": self.result,
        }

class ToolSuccessResult(ToolResult):
    """工具执行成功结果"""
    def __init__(self, result: Any):
        super().__init__(ToolResultStatus.EXECUTE_SUCCESS, result)

class ToolTimeoutResult(ToolResult):
    """工具执行超时结果"""
    def __init__(self, result: Any):
        super().__init__(ToolResultStatus.EXECUTE_TIMEOUT, result)

class ToolErrorResult(ToolResult):
    """工具执行错误结果"""
    def __init__(self, result: Any):
        super().__init__(ToolResultStatus.EXECUTE_ERROR, result)

class ToolCancelledResult(ToolResult):
    """工具执行取消结果"""
    def __init__(self, result: Any):
        super().__init__(ToolResultStatus.EXECUTE_CANCELLED, result)

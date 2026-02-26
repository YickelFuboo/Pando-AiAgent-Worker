from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
from enum import Enum
from app.agents.sweagent.model import ProjectInfo


class BaseTool(ABC):
    """工具基类"""
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
        
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Dict[str, str]]:
        """工具参数定义
        
        Returns:
            Dict[str, Dict[str, str]]: {
                "param_name": {
                    "type": "参数类型",
                    "description": "参数描述"
                }
            }
        """
        pass
        
    @abstractmethod
    async def execute(self, project_info: ProjectInfo, params: Dict[str, Any]) -> Tuple[bool, str]:
        """执行工具调用
        
        Args:
            params: 工具参数

        Returns:
            Tuple[bool, str]:
                - 是否执行成功
                - 执行结果或错误信息
        """
        pass 

    def to_param(self) -> Dict:
        """Convert tool to function call format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
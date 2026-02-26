from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import json

class AgentType(str, Enum):
    """Agent类型枚举"""
    ChatAgent = "ChatAgent"  # 普通聊天智能体
    SweAgent = "SweAgent"  # 代码智能体
    SearchAgent = "RetrievalAgent"  # 信息检索智能体 
    TaskAgent = "TaskAgent"  # 任务规划智能体

    @property
    def chinese_name(self) -> str:
        """获取代理类型的中文名称"""
        names = {
            self.ChatAgent: "通用对话",
            self.SweAgent: "代码开发",
            self.SearchAgent: "智能搜索",
            self.TaskAgent: "任务规划"
        }
        return names.get(self, "未知类型")
    
    @property
    def description(self) -> str:
        """获取代理类型的功能说明"""
        descriptions = {
            self.ChatAgent: "可以进行日常对话、回答问题，支持多轮对话",
            self.SweAgent: "可以进行代码项目分析和生成，支持多种编程语言",
            self.SearchAgent: "可以进行智能搜能，支持搜索和整合多个信息源",
            self.TaskAgent: "可以帮助规划和分解复杂任务，并进行任务执行"
        }
        return descriptions.get(self, "暂无说明")
    
    @classmethod
    def get_all_info(cls) -> list:
        """获取所有代理类型的完整信息"""
        return [
            {
                "type": agent.value,
                "name": agent.chinese_name,
                "description": agent.description
            }
            for agent in cls
        ] 

class AgentState(str, Enum):
    """Agent state enumeration"""
    IDLE = "IDEL"  # Idle state
    RUNNING = "RUNNING"  # Running state
    WAITING = "WAITING"  # Waiting for user input
    ERROR = "ERROR"  # Error state
    FINISHED = "FINISHED"  # Finished state

class AgentResponse(BaseModel):
    """Agent response"""
    status: AgentState
    content: str

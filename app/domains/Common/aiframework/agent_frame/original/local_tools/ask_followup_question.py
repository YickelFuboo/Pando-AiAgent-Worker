from typing import Dict
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult


class AskFollowupQuestion(BaseTool):
    """向用户提问工具"""
    @property
    def name(self) -> str:
        return "ask_followup_question"
        
    @property
    def description(self) -> str:
        return """向用户提问，以收集完成任务所需的其他信息。当您遇到歧义、需要澄清或需要更多细节才能有效进行时，应使用此工具。它允许通过与用户直接沟通来解决交互式问题。明智地使用此工具，在收集必要信息和避免过度来回之间保持平衡。"""
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "你需要向用户确认的问题描述"
                }
            },
            "required": ["question"]
        }    
    async def execute(self, question: str, **kwargs) -> str:
        """Finish the current execution"""
        return ToolSuccessResult(question)  
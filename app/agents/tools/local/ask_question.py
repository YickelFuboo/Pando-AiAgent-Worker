from typing import Dict, Any
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult


class AskQuestion(BaseTool):
    """Ask a question to the user."""
    @property
    def name(self) -> str:
        return "ask_question"
        
    @property
    def description(self) -> str:
        return "Ask a question to the user to collect additional information needed to complete the task."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user."
                }
            },
            "required": ["question"]
        }    

    async def execute(self, question: str, **kwargs) -> ToolResult:
        return ToolSuccessResult(f"The question '{question}' has been asked to the user.")  
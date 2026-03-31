from typing import Any, Dict, List
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult


class AskQuestion(BaseTool):
    """Ask a question to the user."""
    @property
    def name(self) -> str:
        return "ask_question"
        
    @property
    def description(self) -> str:
        return """Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

Usage notes:Do not use this tool unless necessary. You should strive to understand the user's intention and complete the user's task independently. Only use this tool to confirm with the user when it is absolutely necessary without user confirmation.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to ask. For a single question, pass an array with one item.",
                    "items": {"type": "string"},
                }
            },
            "required": ["questions"]
        }    

    async def execute(
        self,
        questions: List[str],
        **kwargs: Any,
    ) -> ToolResult:
        formatted = []
        for q in questions or []:
            text = (q or "").strip()
            formatted.append(f"{text}")
        
        questions_text = "\n".join(formatted)  

        return ToolSuccessResult(f"The question has been asked to the user：{questions_text}")  
        
from typing import Any, TYPE_CHECKING
from app.agents.tools.base import BaseTool
from app.agents.core.subagent import SubAgentManager


class SpawnTool(BaseTool):
    """Tool to spawn a subagent for background task execution."""
    
    def __init__(self, subagent_manager: SubAgentManager):
        self.subagent_manager = subagent_manager
    
    @property
    def name(self) -> str:
        return "spawn"
    
    @property
    def description(self) -> str:
        return (
            "Spawn a subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent will complete the task and report back when done."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
            },
            "required": ["task"],
        }
    
    async def execute(self, task: str, label: str | None = None, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        return await self.subagent_manager.start_task(
            task=task,
            label=label,
        )

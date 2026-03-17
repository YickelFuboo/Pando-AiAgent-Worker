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
            "Spawn a subagent to handle a well-defined subtask in the background. "
            "Use this for tasks that are long-running, tool-intensive, or data-heavy, where the detailed process "
            "does not need to stay in the main agent's context. Typical (but not exclusive) examples include: "
            "summarizing multiple files or a large directory, scanning logs or search results and extracting only "
            "key findings, or running a multi-step investigation (probe environment, run several commands, then summarize). "
            "The subagent should perform detailed work with its own tools and return a short, structured summary "
            "instead of raw full content."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "A single, clear task for the subagent to complete (e.g. 'Summarize the key responsibilities "
                                   "and public APIs of files A, B, and C', or 'Scan recent logs and explain the most likely root cause "
                                   "of failures'). Avoid including raw file contents or very long text here; describe the goal and scope "
                                   "instead of pasting data.",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display in logs/UI, e.g. a directory, feature, or topic name).",
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

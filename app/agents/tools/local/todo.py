import json
from pathlib import Path
from typing import Any,Dict,List,Optional
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolSuccessResult

PROJECT_ROOT=Path(__file__).resolve().parents[4]
DATA_ROOT=PROJECT_ROOT/"data"


def _todo_file(session_id : str)->Path:
    root = DATA_ROOT/"session_todo"/session_id
    root.mkdir(parents=True, exist_ok=True)
    return root/"todo.json"

def _load(path : Path)->List[Dict[str,Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []

def _save(path:Path, todos:List[Dict[str,Any]])->None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


class TodoWriteTool(BaseTool):
    def __init__(self,*,session_id:str=""):
        self._session_id=(session_id or "").strip()

    @property
    def name(self)->str:
        return "todo_write"

    @property
    def description(self)->str:
        return """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multistep tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos. Feel free to edit the todo list based on new information.
6. After completing a task - Mark it complete and add any new follow-up tasks
7. When you start working on a new task, mark the todo as in_progress. Ideally you should only have one todo as in_progress at a time. Complete existing tasks before starting new ones.

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully
   - cancelled: Task no longer needed

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
   - Cancel tasks that become irrelevant

3. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully."""

    @property
    def parameters(self)->Dict[str,Any]:
        return {
            "type":"object",
            "properties":{
                "todos":{
                    "type":"array",
                    "items":{
                        "type":"object",
                        "properties":{
                            "content":{
                                "type":"string",
                                "description":"Brief description of the task",
                            },
                            "status":{
                                "type":"string",
                                "enum":["pending","in_progress","completed","cancelled"],
                                "description":"Current status of the task",
                            },
                            "priority":{
                                "type":"string",
                                "enum":["high","medium","low"],
                                "description":"Priority level of the task",
                            },
                        },
                        "required":["content","status","priority"],
                    },
                    "description":"The updated todo list",
                },
            },
            "required":["todos"],
        }

    async def execute(self, todos:List[Dict[str,Any]], **kwargs:Any)->ToolResult:
        if not self._session_id:
            return ToolErrorResult("todo_write: session_id is required")

        p = _todo_file(self._session_id)
        _save(p, todos)
        remaining = len([t for t in todos if t.get("status")!="completed"])
        output = "\n".join([
            f"<path>{p}</path>",
            f"<remaining>{remaining}</remaining>",
            "<todos>",
            json.dumps(todos, ensure_ascii=False, indent=2),
            "</todos>",
        ])
        return ToolSuccessResult(output)


class TodoReadTool(BaseTool):
    def __init__(self,*,session_id:str=""):
        self._session_id=(session_id or "").strip()

    @property
    def name(self)->str:
        return "todo_read"

    @property
    def description(self)->str:
        return """Use this tool to read the current to-do list for the session. This tool should be used proactively and frequently to ensure that you are aware of
the status of the current task list. You should make use of this tool as often as possible, especially in the following situations:
- At the beginning of conversations to see what's pending
- Before starting new tasks to prioritize work
- When the user asks about previous tasks or plans
- Whenever you're uncertain about what to do next
- After completing tasks to update your understanding of remaining work
- After every few messages to ensure you're on track

Usage:
- This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like "input" or "empty". LEAVE IT BLANK.
- Returns a list of todo items with their status, priority, and content
- Use this information to track progress and plan next steps
- If no todos exist yet, an empty list will be returned"""

    @property
    def parameters(self)->Dict[str,Any]:
        return {"type":"object","properties":{}}

    async def execute(self,**kwargs:Any)->ToolResult:
        if not self._session_id:
            return ToolErrorResult("todo_read: session_id is required")

        p = _todo_file(self._session_id)
        todos = _load(p)
        remaining = len([t for t in todos if t.get("status")!="completed"])
        output="\n".join([
            f"<path>{p}</path>",
            f"<remaining>{remaining}</remaining>",
            "<todos>",
            json.dumps(todos,ensure_ascii=False,indent=2),
            "</todos>",
        ])
        return ToolSuccessResult(output)


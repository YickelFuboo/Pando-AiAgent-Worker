import asyncio
import json
from typing import Any,Dict,List,Optional
from app.agents.tools.base import BaseTool
from app.agents.tools.factory import ToolsFactory
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolResultStatus,ToolSuccessResult

MAX_BATCH_SIZE=25
DISALLOWED_TOOLS={"batch_tools","apply_patch"}
FILTERED_FROM_SUGGESTIONS={"invalid","apply_patch","batch_tools"}


class BatchTool(BaseTool):
    def __init__(self,tools_factory:Optional[ToolsFactory]=None):
        self._tools_factory = tools_factory

    @property
    def name(self)->str:
        return "batch_tools"

    @property
    def description(self)->str:
        return """Executes multiple independent tool calls concurrently to reduce latency.

Payload Format:
{"tool_calls":[{"tool":"read_file","parameters":{"path":"/abs/path/a.txt"}},{"tool":"grep","parameters":{"pattern":"TODO","path":"/abs/path"}},{"tool":"exec","parameters":{"command":"git status"}}]}

Notes:
- 1-25 tool calls per batch
- All calls start in parallel; ordering is not guaranteed
- Partial failures do not stop other tool calls
- Do NOT use this tool within another batch_tools call

Good Use Cases:
- Read/search multiple files
- Run multiple independent shell commands
- Perform independent edits on different files

When NOT to Use:
- Operations that depend on prior tool output (for example, create then read the same file)
- Ordered stateful mutations where sequence matters"""

    @property
    def parameters(self)->Dict[str,Any]:
        return {
            "type":"object",
            "properties":{
                "tool_calls":{
                    "type":"array",
                    "items":{
                        "type":"object",
                        "properties":{
                            "tool":{"type":"string"},
                            "parameters":{"type":"object"},
                        },
                        "required":["tool","parameters"],
                    },
                    "minItems":1,
                },
            },
            "required":["tool_calls"],
        }

    async def execute(self, tool_calls:List[Dict[str,Any]], **kwargs:Any)->ToolResult:
        if self._tools_factory is None:
            return ToolErrorResult("batch tool is unavailable: tools factory not configured")

        calls = tool_calls[:MAX_BATCH_SIZE]
        discarded = tool_calls[MAX_BATCH_SIZE:]

        async def _run(call:Dict[str,Any])->Dict[str,Any]:
            tool_name = call.get("tool")
            params = call.get("parameters")
            if not isinstance(tool_name, str) or not tool_name:
                return {"tool":str(tool_name), "success":False, "error":"tool must be a non-empty string"}
            if tool_name in DISALLOWED_TOOLS:
                return {"tool":tool_name, "success":False, "error":f"Tool '{tool_name}' is not allowed in batch"}
            if not isinstance(params, dict):
                return {"tool":tool_name, "success":False, "error":"parameters must be an object"}
            if not self._tools_factory.has_tool(tool_name):
                available_tools=[name for name in self._tools_factory.list_tool_names() if name not in FILTERED_FROM_SUGGESTIONS]
                return {
                    "tool":tool_name,
                    "success":False,
                    "error":f"Tool '{tool_name}' not found. Available tools: {', '.join(sorted(available_tools))}",
                }

            result=await self._tools_factory.execute(tool_name=tool_name, tool_params=params)
            ok = result.status == ToolResultStatus.EXECUTE_SUCCESS
            item={"tool":tool_name,"success":ok,"status":result.status.value}
            if ok:
                item["metadata"]=getattr(result,"metadata",None)
            else:
                item["error"]=f"{result.result}"
            return item

        results = await asyncio.gather(*[_run(call) for call in calls])
        for call in discarded:
            results.append({
                "tool":f"{call.get('tool')}",
                "success":False,
                "error":f"Maximum of {MAX_BATCH_SIZE} tools allowed in batch",
            })

        success_count = sum(1 for item in results if item.get("success"))  # noqa: PERF401
        failed_count = len(results) - success_count
        if failed_count > 0:
            output=f"Executed {success_count}/{len(results)} tools successfully. {failed_count} failed."
        else:
            output=f"All {success_count} tools executed successfully."

        output_body="\n".join([
            "<summary>",
            output,
            "</summary>",
            f"<total_calls>{len(results)}</total_calls>",
            f"<successful>{success_count}</successful>",
            f"<failed>{failed_count}</failed>",
            "<details>",
            json.dumps(results, ensure_ascii=False),
            "</details>",
        ])
        return ToolSuccessResult(output_body)


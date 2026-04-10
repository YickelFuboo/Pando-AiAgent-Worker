from typing import Any
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class WebSearchTool(BaseTool):
    """Tavily Web 搜索工具，返回标题、URL 与摘要。"""

    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self._client = TavilySearch()

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return titles, URLs, and snippets."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> ToolResult:
        try:
            n = min(max(count or self.max_results, 1), 10)
        except Exception:
            n = self.max_results

        try:
            results = await self._client.search(query)
        except Exception as e:
            return ToolErrorResult(f"Error calling Tavily: {e}")

        if not results:
            return ToolSuccessResult(f"No results for: {query}")

        lines: list[str] = [f"Results for: {query}\n"]
        for i, item in enumerate(results[:n], 1):
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("content", "")
            lines.append(f"{i}. {title}\n   {url}")
            if desc:
                lines.append(f"   {desc}")

        return ToolSuccessResult("\n".join(lines))
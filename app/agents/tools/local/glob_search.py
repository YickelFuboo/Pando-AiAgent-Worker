import fnmatch
import re
from pathlib import Path
from typing import Any,Dict,List,Optional,Tuple
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolSuccessResult


class GlobTool(BaseTool):
    @property
    def name(self) -> str:
        return "glob_search"

    @property
    def description(self) -> str:
        return """Fast file pattern matching tool for local projects of any type.

Usage:
- Supports glob patterns like "**/*.js", "src/**/*.ts", "*.md", or "data/**/*.csv".
- Returns file paths sorted by modification time (newest first).
- Results are limited to 100 paths.
- Use this tool when you need to find files by name patterns.
- If you expect many iterative search rounds, prefer the task tool for broader exploration.
- When you already know multiple likely patterns, run multiple glob calls in parallel.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match files against"
                },
                "path": {
                    "type": "string",
                    "description": "Optional absolute directory path to search in."
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: Optional[str] = None, **kwargs: Any) -> ToolResult:
        if not pattern:
            return ToolErrorResult("pattern is required")

        try:
            if path:
                search = Path(path).expanduser()
                if not search.is_absolute():
                    return ToolErrorResult("path must be an absolute directory path")
                search = search.resolve()
            else:
                search = Path.cwd().resolve()
            if not search.exists() or not search.is_dir():
                return ToolErrorResult(f"glob failed: directory does not exist: {search}")
        except Exception as e:
            return ToolErrorResult(f"glob failed: {e}")

        limit = 100
        items: List[Tuple[str, float]] = []
        try:
            for p in search.rglob("*"):
                if not p.is_file():
                    continue

                rel = str(p.relative_to(search)).replace("\\", "/")
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    items.append((str(p), mtime))
        except Exception as e:
            return ToolErrorResult(f"glob failed: {e}")

        items.sort(key=lambda x: x[1], reverse=True)
        truncated = len(items) > limit
        final = items[:limit]
        if not final:
            return ToolSuccessResult("No files found")

        out = "\n".join([p for p, _ in final])
        if truncated:
            out += "\n\n(Results are truncated: showing first 100 results. Consider using a more specific path or pattern.)"
        return ToolSuccessResult(out)

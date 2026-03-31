import fnmatch
import re
from pathlib import Path
from typing import Any,Dict,List,Optional,Tuple
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolSuccessResult

MAX_LINE_LENGTH = 2000


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


class GrepTool(BaseTool):
    @property
    def name(self) -> str:
        return "grep_search"

    @property
    def description(self) -> str:
        return """Fast content search tool for local projects of any type.

Usage:
- Searches file contents using regular expressions.
- Supports full regex syntax, for example: "log.*Error", "function\\s+\\w+".
- Use `include` to filter files by pattern, for example: "*.js", "*.{ts,tsx}", "*.md", "*.csv".
- Returns matching files with line numbers, grouped by file and sorted by modification time.
- Use this tool when you need to find files containing specific patterns.
- If you need exact counting or advanced match statistics, prefer the bash tool with `rg` directly.
- If the search is open-ended and may require multiple rounds of glob and grep, prefer the task tool.
- Results are limited to 100 matches.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for in file contents"
                },
                "path": {
                    "type": "string",
                    "description": "Optional absolute directory path to search in."
                },
                "include": {
                    "type": "string",
                    "description": "File glob to include (e.g. *.py, *.{ts,tsx})"
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
        **kwargs: Any
    ) -> ToolResult:
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
                return ToolErrorResult(f"grep failed: directory does not exist: {search}")
        except Exception as e:
            return ToolErrorResult(f"grep failed: {e}")

        try:
            rx = re.compile(pattern)
        except re.error as e:
            return ToolErrorResult(f"invalid regex: {e}")

        def include_match(p: Path) -> bool:
            if not include:
                return True

            inc = include
            if inc.startswith("{") and inc.endswith("}"):
                inc = "*." + inc[1:-1]
            if "{" in inc and "}" in inc:
                parts = [part.strip() for part in inc.split(",") if part.strip()]
                return any(Path(p.name).match(part) for part in parts)
            return Path(p.name).match(inc) or Path(str(p)).match(inc)

        matches: List[Tuple[str, float, int, str]] = []
        try:
            for fp in search.rglob("*"):
                if not fp.is_file():
                    continue
                if not include_match(fp):
                    continue
                try:
                    mtime = fp.stat().st_mtime
                except OSError:
                    mtime = 0.0
                try:
                    with fp.open("r", encoding="utf-8", errors="replace") as f:
                        for idx, line in enumerate(f, 1):
                            if rx.search(line):
                                text = line.rstrip("\n\r")
                                if len(text) > MAX_LINE_LENGTH:
                                    text = text[:MAX_LINE_LENGTH] + "..."
                                matches.append((str(fp), mtime, idx, text))
                except OSError:
                    continue
        except Exception as e:
            return ToolErrorResult(f"grep failed: {e}")

        if not matches:
            return ToolSuccessResult("No files found")

        matches.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
        limit = 100
        truncated = len(matches) > limit
        final = matches[:limit]
        total = len(matches)
        out_lines = [f"Found {total} matches" + (f" (showing first {limit})" if truncated else "")]

        current = ""
        for fp, _, ln, text in final:
            if current != fp:
                if current:
                    out_lines.append("")
                current = fp
                out_lines.append(f"{fp}:")
            out_lines.append(f"  Line {ln}: {text}")

        if truncated:
            out_lines.append("")
            out_lines.append(f"(Results truncated: showing {limit} of {total} matches ({total-limit} hidden). Consider using a more specific path or pattern.)")

        return ToolSuccessResult("\n".join(out_lines))

from pathlib import Path
from typing import Any,Dict,List,Optional,Set
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolSuccessResult


IGNORE_PATTERNS = [
    "node_modules",
    "__pycache__",
    ".git",
    "dist",
    "build",
    "target",
    "vendor",
    "bin",
    "obj",
    ".idea",
    ".vscode",
    ".zig-cache",
    "zig-out",
    ".coverage",
    "coverage",
    "tmp",
    "temp",
    ".cache",
    "cache",
    "logs",
    ".venv",
    "venv",
    "env",
]

LIMIT = 100


class ListCodeFilesTool(BaseTool):
    @property
    def name(self) -> str:
        return "list_code_files"

    @property
    def description(self) -> str:
        return """Lists files and directories in a given path (code-oriented tree view).

Usage:
- `path` must be an absolute directory path when provided.
- Omit `path` to use the current working directory.
- You can provide `ignore` as an array of glob patterns to skip paths.
- This tool recursively scans and returns a simple tree, while skipping common build/cache folders.
- Prefer `glob` and `grep` when you already know which directories or patterns to search.
- Results are limited to 100 files.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional absolute directory path to list."
                },
                "ignore": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional ignore glob patterns."
                },
            },
        }

    async def execute(
        self,
        path: Optional[str] = None,
        ignore: Optional[List[str]] = None,
        **kwargs: Any
    ) -> ToolResult:
        try:
            if path:
                root = Path(path).expanduser()
                if not root.is_absolute():
                    return ToolErrorResult("path must be an absolute directory path")
                root = root.resolve()
            else:
                root = Path.cwd().resolve()
            if not root.exists():
                return ToolErrorResult(f"directory not found: {root}")
            if not root.is_dir():
                return ToolErrorResult(f"not a directory: {root}")
        except Exception as e:
            return ToolErrorResult(f"list_code_files failed: {e}")

        extra = set(ignore or [])
        files: List[str] = []

        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue

                rel = str(p.relative_to(root)).replace("\\", "/")
                parts = rel.split("/")
                if any(part in IGNORE_PATTERNS for part in parts[:-1]):
                    continue
                if any(Path(rel).match(g) for g in extra):
                    continue
                files.append(rel)
                if len(files) >= LIMIT:
                    break
        except Exception as e:
            return ToolErrorResult(f"list_code_files failed: {e}")

        dirs: Set[str] = set()
        files_by_dir: Dict[str, List[str]] = {}
        for rel in files:
            d = str(Path(rel).parent).replace("\\", "/")
            if d == ".":
                d = "."
            parts = [] if d == "." else d.split("/")
            for i in range(len(parts) + 1):
                dp = "." if i == 0 else "/".join(parts[:i])
                dirs.add(dp)
            files_by_dir.setdefault(d, []).append(Path(rel).name)

        def render(dir_path: str, depth: int) -> str:
            indent = "  " * depth
            out = ""
            if depth > 0:
                out += f"{indent}{Path(dir_path).name}/\n"
            children = sorted([d for d in dirs if Path(d).parent.as_posix() == Path(dir_path).as_posix() and d != dir_path])
            for child in children:
                out += render(child, depth + 1)
            child_indent = "  " * (depth + 1)
            for f in sorted(files_by_dir.get(dir_path, [])):
                out += f"{child_indent}{f}\n"
            return out

        output = str(root).replace("\\", "/") + "/\n" + render(".", 0)
        truncated = len(files) >= LIMIT
        if truncated:
            output += "\n(Results are truncated: showing first 100 files.)"
        return ToolSuccessResult(output)

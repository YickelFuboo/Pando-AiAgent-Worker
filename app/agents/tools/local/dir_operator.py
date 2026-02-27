from typing import Any
from pathlib import Path
import logging
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class ListDirTool(BaseTool):
    """Tool to list directory contents."""
    @property
    def name(self) -> str:
        return "list_dir"
    
    @property
    def description(self) -> str:
        return "List the contents of a directory."
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs: Any) -> ToolResult:
        try:
            if not path or not path.strip():
                logging.error("Invalid parameters: path=%r", path)
                return ToolErrorResult("Missing path parameter")

            dir_path = Path(path).expanduser().resolve()
            if not dir_path.exists():
                logging.warning("Directory not found: %s", dir_path)
                return ToolErrorResult(f"Directory not found: {path}")
            
            if not dir_path.is_dir():
                logging.warning("Not a directory: %s", dir_path)
                return ToolErrorResult(f"Not a directory: {path}")

            entries = []
            for p in sorted(dir_path.iterdir()):
                prefix = "📁 " if p.is_dir() else "📄 "
                entries.append(f"{prefix}{p.name}")
            if not entries:
                return ToolSuccessResult(f"Directory {path} is empty")

            return ToolSuccessResult("\n".join(entries))
        except PermissionError as e:
            logging.error("Permission error listing directory: path=%s, error=%s", path, e)
            return ToolErrorResult(f"Error: {e}")
        except Exception as e:
            logging.error("Error listing directory: path=%s, error=%s", path, e)
            return ToolErrorResult(f"Error listing directory: {str(e)}")

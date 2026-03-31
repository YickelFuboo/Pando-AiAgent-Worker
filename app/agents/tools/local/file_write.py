import os
from typing import Dict,Any,Optional
import logging
import difflib
from pathlib import Path
from ..base import BaseTool
from ..schemes import ToolResult,ToolSuccessResult,ToolErrorResult


class ReadFileTool(BaseTool):
    """文件读取工具"""
    @property
    def name(self) -> str:
        return "read_file"
        
    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",   
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to read."
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional line number to start reading from (1-indexed)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional maximum number of lines to read."
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, offset: Optional[int] = None, limit: Optional[int] = None, **kwargs) -> ToolResult:
        try:
            if not path or not path.strip():
                logging.error("参数错误: path=%r", path)
                return ToolErrorResult("Missing path parameter")
            if offset is not None and offset < 1:
                return ToolErrorResult("offset must be greater than or equal to 1")
            if limit is not None and limit < 1:
                return ToolErrorResult("limit must be greater than or equal to 1")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("文件不存在: path=%s", file_path)
                return ToolErrorResult(f"File not found: {path}")
                
            if not file_path.is_file():
                logging.warning("不是文件路径: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                if offset is None and limit is None:
                    content = f.read()
                else:
                    lines = f.readlines()
                    start = (offset or 1) - 1
                    end = start + limit if limit is not None else len(lines)
                    if start >= len(lines) and not (len(lines) == 0 and start == 0):
                        return ToolErrorResult(
                            f"Offset {offset} is out of range for this file ({len(lines)} lines)"
                        )
                    sliced = lines[start:end]
                    content = "".join(
                        f"{idx + start + 1}: {line}" for idx, line in enumerate(sliced)
                    )
            return ToolSuccessResult(content)
            
        except Exception as e:
            logging.error("读取文件异常: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to read file: {str(e)}") 
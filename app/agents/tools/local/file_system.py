import os
from typing import Dict, Any, Optional
import logging
import difflib
from pathlib import Path
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult


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
                }
            },
            "required": ["path"]
        }
    
    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            if not path or not path.strip():
                logging.error("参数错误: path=%r", path)
                return ToolErrorResult("Missing path parameter")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("文件不存在: path=%s", file_path)
                return ToolErrorResult(f"File not found: {path}")
                
            if not file_path.is_file():
                logging.warning("不是文件路径: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return ToolSuccessResult(content)
            
        except Exception as e:
            logging.error("读取文件异常: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to read file: {str(e)}") 

class WriteFileTool(BaseTool):
    """写入文件工具"""  
    @property
    def name(self) -> str:
        return "write_file"   

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to write to."
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file."
                }
            },
            "required": ["path", "content"]
        }  

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("参数错误: path=%r, content=%r", path, content)
                return ToolErrorResult("Missing path or content parameter")     

            file_path = Path(path).expanduser().resolve()

            file_path.parent.mkdir(parents=True, exist_ok=True)
                  
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolSuccessResult(f"Successfully wrote {len(content)} bytes to {path}")
            
        except Exception as e:
            logging.error("Failed to write file: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to write file: {str(e)}") 

class ReleaseFileTextTool(BaseTool):
    """Replace text in a file."""
    @property
    def name(self) -> str:
        return "release_file_text"
    
    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> ToolResult:
        try:
            if not path or not path.strip() or not old_text or not new_text:
                logging.error("Invalid parameters: path=%r, old_text=%r, new_text=%r", path, old_text, new_text)
                return ToolErrorResult("Missing path, old_text or new_text parameter")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("File not found: path=%s", file_path)
                return ToolErrorResult(f"File not found: {path}")

            if not file_path.is_file():
                logging.warning("Not a file: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                logging.warning(
                    "old_text not found in content: old_text=%r, path=%s",
                    old_text,
                    file_path,
                )
                return ToolErrorResult(self._not_found_message(old_text, content, path))
            
            count = content.count(old_text)
            if count > 1:
                logging.warning(
                    "old_text appears %d times in %s. Please provide more context.",
                    count,
                    file_path,
                )
                return ToolErrorResult(
                    f"old_text appears {count} times. Please provide more context to make it unique."
                )

            new_content = content.replace(old_text, new_text, 1)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolSuccessResult(f"Successfully edited {path}")
        except PermissionError as e:
            logging.error("权限错误: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Permission error: {str(e)}")
        except Exception as e:
            logging.error("编辑文件异常: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to edit file: {str(e)}")

    @staticmethod
    def _not_found_message(old_text: str, content: str, path: str) -> str:
        """Build a helpful error when old_text is not found."""
        lines = content.splitlines(keepends=True)
        old_lines = old_text.splitlines(keepends=True)
        window = len(old_lines)

        best_ratio, best_start = 0.0, 0
        for i in range(max(1, len(lines) - window + 1)):
            ratio = difflib.SequenceMatcher(None, old_lines, lines[i : i + window]).ratio()
            if ratio > best_ratio:
                best_ratio, best_start = ratio, i

        if best_ratio > 0.5:
            diff = "\n".join(difflib.unified_diff(
                old_lines, lines[best_start : best_start + window],
                fromfile="old_text (provided)", tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."

class InsertFileTool(BaseTool):
    """Insert content into a file."""  
    @property
    def name(self) -> str:
        return "insert_file"   
        
    @property
    def description(self) -> str:
        return "Insert content into a file at the given position."
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to insert content into."
                },
                "position": {
                    "type": "integer",
                    "description": "The line number to insert content at. If None, will insert at end of file."
                },
                "content": {
                    "type": "string",
                    "description": "The content to insert into the file."
                }
            },
            "required": ["path", "content"]
        }      

            
    async def execute(self, path: str, position: Optional[int], content: str, **kwargs) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("Invalid parameters: path=%r, content=%r", path, content)
                return ToolErrorResult("Invalid parameters")     
            
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.error("File not found: %s", file_path)
                return ToolErrorResult("File not found")
            
            if not file_path.is_file():
                logging.error("Not a file: %s", file_path)
                return ToolErrorResult("Not a file")

            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            if position is None:
                position = len(lines)
            elif position < 0 or position > len(lines):
                logging.error(
                    "Invalid position: %d, file has %d lines", position, len(lines)
                )
                return ToolErrorResult(f"Invalid position: {position}, file has {len(lines)} lines")
            
            with open(file_path, "r+", encoding="utf-8") as f:
                f.writelines(lines[:position])
                f.write(content)
                if not content.endswith("\n"):
                    f.write("\n")
                f.writelines(lines[position:])
            
            return ToolSuccessResult(f"Successfully inserted {len(content)} bytes at line {position} in file {path}")
            
        except Exception as e:
            logging.error("Failed to insert content: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to insert content: {str(e)}") 
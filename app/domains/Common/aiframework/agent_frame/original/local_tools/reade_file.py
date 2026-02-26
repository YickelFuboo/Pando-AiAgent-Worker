import os
from typing import Dict
from app.logger import Logger
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult

class FileReaderTool(BaseTool):
    """文件读取工具"""
    @property
    def name(self) -> str:
        return "read_file"
        
    @property
    def description(self) -> str:
        return "读取指定文件的内容"
        
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",   
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件的完整路径"
                }
            },
            "required": ["file_path"]
        }
    async def execute(self, file_path: str, **kwargs) -> Tuple[bool, str]:
        try:
            if not file_path:
                Logger.error(f"参数错误: full_path={file_path}")
                return ToolErrorResult("Missing path parameter")

            if not os.path.exists(file_path):
                Logger.warning(f"文件不存在: file_path={file_path}")
                return ToolErrorResult(f"File not found: {file_path}")
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return ToolSuccessResult(content)
            
        except Exception as e:
            Logger.error(f"读取文件异常: file_path={file_path}, error={e}")
            return ToolErrorResult(f"Failed to read file: {str(e)}") 
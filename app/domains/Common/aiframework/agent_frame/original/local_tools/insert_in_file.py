from typing import Dict, Optional
import os
from app.logger import logger
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class InsertInFileTool(BaseTool):
    """插入内容到文件工具"""  
    @property
    def name(self) -> str:
        return "insert_in_file"        
    @property
    def description(self) -> str:
        return """请求将内容插入到指定路径的文件中, 如果文件存在，它将被提供的内容插入。
    1. 如下情况下可以考虑使用本工具：当需要已有文件中插入片段时，可使用本方法。如：对于代码Agent场景，在源代码文件中新增类或结构体定义、新增方法或函数定义等。
    2. 使用注意事项：
        - 使用本工具时如果未指定文件位置，默认插入到源文件末尾。
        - 如果您只需要对现有文件中内容进行小幅更改，而不是新增完整的片段，请避免使用本工具。"""
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "需要插入内容的文件的完整路径"
                },
                "position": {
                    "type": "integer",
                    "description": "插入位置行号"
                },
                "content": {
                    "type": "string",
                    "description": "要插入到文件的内容。始终提供文件的完整预期内容，不得有任何截断或遗漏。您必须包含文件的所有部分，即使它们没有被修改。"
                }
            },
            "required": ["file_path", "content"]
        }              
    async def execute(self, file_path: str, position: Optional[int], content: str, **kwargs) -> ToolResult:
        """Insert content into file at specified position
        
        Args:
            file_path: Target file path
            position: Line number to insert at (1-based), if None will insert at end of file
            content: Content to insert
            
        Returns:
            ToolResult: Result of the operation
        """
        try:
            if not file_path or not content:
                logger.error(f"Invalid parameters: file_path={file_path}, content={content}")
                return ToolErrorResult("Invalid parameters")     
            
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return ToolErrorResult("File not found")
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # If no position specified, insert at end of file
            if position is None:
                position = len(lines)
                logger.info(f"No position specified, will insert at end of file (line {position})")
            elif position < 0 or position > len(lines):
                logger.error(f"Invalid position: {position}, file has {len(lines)} lines")
                return ToolErrorResult(f"Invalid position: {position}, file has {len(lines)} lines")
            
            # Write file using r+ mode
            with open(file_path, 'r+', encoding='utf-8') as f:
                # Write content before position
                f.writelines(lines[:position])
                # Write new content
                f.write(content)
                if not content.endswith('\n'):
                    f.write('\n')
                # Write content after position
                f.writelines(lines[position:])
            
            logger.info(f"Successfully inserted content at line {position} in file {file_path}")
            return ToolSuccessResult(f"Successfully inserted content at line {position}")
            
        except Exception as e:
            logger.error(f"Failed to insert content: {str(e)}")
            return ToolErrorResult(f"Failed to insert content: {str(e)}") 
from typing import Dict, Any, Tuple
from app.logger import logger
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class WriteToFileTool(BaseTool):
    """写入文件工具"""  
    @property
    def name(self) -> str:
        return "write_to_file"        
    @property
    def description(self) -> str:
        return """请求将内容写入指定路径的文件。如果文件存在，它将被提供的内容覆盖；如果文件不存在，它将被创建。
    1. 此工具将自动创建写入文件所需的任何目录。
    2. 如下情况下可以考虑使用本工具：
        - 初始文件创建，例如构建新项目时。
        - 覆盖要一次替换整个内容的大型样板文件。
        - 当您需要完全重构文件的内容或更改其基本组织时。
    3. 使用注意事项：
        - 使用本工具需要提供文件的完整最终内容。
        - 如果您只需要对现有文件进行小幅更改，请考虑使用其它小范围修改工具，以避免不必要地重写整个文件。
        - 虽然本工具不应该是您的默认选择，但当情况真正需要时，不要犹豫使用它。"""
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "需要写入内容的文件的完整路径"
                },
                "content": {
                    "type": "string",
                    "description": "需要写入文件的内容"
                }
            },
            "required": ["file_path", "content"]
        }              
    async def execute(self, file_path: str, content: str, **kwargs ) -> Tuple[bool, str]:
        try:
            if not file_path or not content:
                logger.error(f"参数错误: file_path={file_path}, content={content}")
                return ToolErrorResult("参数错误: file_path={file_path}, content={content}")     
                  
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"文件 {file_path} 写入成功")
            return ToolSuccessResult(f"文件 {file_path} 写入成功")
            
        except Exception as e:
            logger.error(f"写入文件异常: {str(e)}")
            return ToolErrorResult(f"Failed to write file: {str(e)}") 
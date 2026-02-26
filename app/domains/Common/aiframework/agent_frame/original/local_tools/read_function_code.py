from typing import Dict
import os
from app.logger import logger
from app.agents.sweagent.model import ProjectInfo
from app.context.codebase.codegraph.query import CodeGraphQuery
from app.context.codebase.codegraph.scheme import FunctionRequest
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class ReadFunctionCodeTool(BaseTool):
    """读取函数代码工具"""
    @property
    def name(self) -> str:
        return "read_function_code"
        
    @property
    def description(self) -> str:
        return """本工具用于代码Agent场景，通过本工具读取指定路径的文件中、指定名称的函数（Function）或方法（method）实现源代码。当你需要修改指定函数或方法时，可以使用本工具获取修改前的源代码，然后在源代码基础上进行修改。"""
        
    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",
            "properties": {
                "project_info": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "项目名称"
                        },
                        "project_dir": {
                            "type": "string",
                            "description": "项目根目录的绝对路径"
                        },
                        "owner": {
                            "type": "string",
                            "description": "项目所有者"
                        },
                        "project_description": {
                            "type": "string",
                            "description": "项目描述"
                        }
                    },
                    "required": ["project_name", "project_dir", "owner", "project_description"]
                },
                "file_path": {
                    "type": "string",
                    "description": "函数或方法所在文件的相对路径（相对于项目根目录）"
                },
                "function_name": {
                    "type": "string",
                    "description": "函数或方法名称"
                }
            },
            "required": ["project_info", "file_path", "function_name"]
        }              
        
    async def execute(self, project_info: ProjectInfo, file_path: str, function_name: str, **kwargs) -> ToolResult:
        """Execute function code reading
        
        Args:
            file_path: Source file path
            function_name: Function name to read
            
        Returns:
            ToolResult: Result containing function information
        """
        try:
            # 确保 project_info 是 ProjectInfo 实例
            if isinstance(project_info, dict):
                project_info = ProjectInfo(**project_info)

            if not project_info or not project_info.project_dir or not file_path or not function_name:
                logger.error(f"params error: project_info={project_info}, file_path={file_path}, function_name={function_name}")
                return ToolErrorResult("params error")
            
            # file_path 调整为相对于 project_info.project_dir的路径
            # file_path = os.path.relpath(file_path, project_info.project_dir)
            
            # 查询函数代码
            with CodeGraphQuery() as query:
                response = await query.query_functions_code(
                    project_info=project_info,
                    file_functions=[
                        FunctionRequest(
                            file_path=file_path,
                            function_name=function_name
                        )
                    ]
                )
            
            if not response.result:
                logger.warning(f"query function code failed: {response.message}")
                return ToolErrorResult(response.message)
                
            if not response.content:
                logger.info(f"function {function_name} not found in {file_path}")
                return ToolErrorResult(f"function {function_name} not found in {file_path}")
                
            # 格式化输出
            """
            function_info = response.content[0]
            output = f"Function: {function_info['name']}\n"
            output += f"File: {function_info['file_path']}\n"
            if function_info['docstring']:
                output += f"\nDocstring:\n{function_info['docstring']}\n"
            output += f"\nSource Code:\n{function_info['source_code']}"
            
            return ToolSuccessResult(output)
            """
            return ToolSuccessResult(response.content)
            
        except Exception as e:
            logger.error(f"Failed to read function code: {str(e)}")
            return ToolErrorResult(f"Failed to read function code: {str(e)}") 
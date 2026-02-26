from typing import Dict
from app.logger import logger
from app.agents.sweagent.model import ProjectInfo
from app.context.codebase.codegraph.query import CodeGraphQuery
from app.context.codebase.codegraph.scheme import ClassRequest
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class ReadClassCodeTool(BaseTool):
    """读取类代码工具"""
    @property
    def name(self) -> str:
        return "read_class_code"
    @property
    def description(self) -> str:
        return """本工具用于代码Agent场景，通过本命令读取指定路径的文件中、指定名称的类（Class）或结构体（Struct）实现源代码。当你需要修改指定类或结构体时，可以调用本工具获取修改前的源代码，然后在源代码基础上进行修改。"""
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
                    "description": "类或结构体所在文件的相对路径（相对于项目根目录）"
                },
                "class_name": {
                    "type": "string",
                    "description": "类或结构体名称"
                }
            },
            "required": ["project_info", "file_path", "class_name"]
        }              
        
    async def execute(self, project_info: ProjectInfo, file_path: str, class_name: str, **kwargs) -> ToolResult:
        """Execute class code reading
        
        Args:
            file_path: Source file path
            class_name: Class name to read
        Returns:
            ToolResult: Result containing class information
        """
        try:
            # 确保 project_info 是 ProjectInfo 实例
            if isinstance(project_info, dict):
                project_info = ProjectInfo(**project_info)
                
            if not project_info or not project_info.project_dir or not file_path or not class_name:
                logger.error(f"params error: project_info={project_info}, file_path={file_path}, class_name={class_name}")
                return ToolErrorResult("params error")        
                      
            # file_path 调整为相对于 project_info.project_dir的路径
            # file_path = os.path.relpath(file_path, project_info.project_dir)
            # 查询类代码
            with CodeGraphQuery() as query:
                response = await query.query_class_code(
                    project_info=project_info,
                    file_classes=[
                        ClassRequest(
                            file_path=file_path,
                            class_name=class_name
                        )
                    ]
                )
            
            if not response.result:
                logger.warning(f"query class code failed: {response.message}")
                return ToolErrorResult(response.message)
                
            if not response.content or not response.content['classes'].get(file_path):
                logger.info(f"class {class_name} not found in {file_path}")
                return ToolErrorResult(f"Class {class_name} not found in {file_path}")
                
            return ToolSuccessResult(response.content)
            
        except Exception as e:
            logger.error(f"Failed to read class code: {str(e)}")
            return ToolErrorResult(f"Failed to read class code: {str(e)}") 
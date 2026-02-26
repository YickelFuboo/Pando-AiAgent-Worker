from typing import Dict
import json
from app.logger import Logger
from app.agents.sweagent.model import ProjectInfo
from app.context.codebase.codegraph.query import CodeGraphQuery
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class ReadProjectStructTool(BaseTool):
    """读取项目结构工具"""
    @property
    def name(self) -> str:
        return "read_project_struct"
        
    @property
    def description(self) -> str:
        return """本工具用于代码Agent场景，通过本命令请求获取指定目录代码项目的框架结构，包含模块（文件夹）和文件结构，以及模块和文件的主要功能描述。该工具提供了对代码库结构和重要构造的见解，封装了对理解整体架构至关重要的高级概念和关系，是理解代码库结构和重要构造的必备工具，方便智能工具根据用户需求初步分析哪些模块或文件与需求相关，进一步通过read_file_summary、read_function_code、read_class_code等工具进一步获取详细信息。"""
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
                }
            },
            "required": ["project_info"]
        } 
    async def execute(self, project_info: ProjectInfo, **kwargs) -> ToolResult:
        try:  
            # 确保 project_info 是 ProjectInfo 实例
            if isinstance(project_info, dict):
                project_info = ProjectInfo(**project_info)

            if not project_info or not project_info.project_dir:
                Logger.error(f"参数错误: project_info={project_info}")
                return ToolErrorResult("Project ID is required")

            # 查询项目结构
            with CodeGraphQuery() as query:
                response = await query.query_project_summary(project_info)
            
            if not response.result:
                Logger.error(f"查询项目结构失败: {response.message}")
                return ToolErrorResult(response.message)
                
            if not response.content:
                Logger.warning(f"查询项目结构失败: {response.message}")
                return ToolErrorResult("No project structure found")
            
            # 格式化输
            """
            output = "Project Structure:\n"
            
            def format_folder(folder: Dict, level: int = 0):
                indent = "  " * level
                result = f"{indent}- {folder['name']}/\n"
                if folder.get('description'):
                    result += f"{indent}  Description: {folder['description']}\n"
                    
                # 添加文件
                if folder.get('files'):
                    for file in folder['files']:
                        result += f"{indent}  - {file['name']}\n"
                        
                # 递归处理子文件夹
                if folder.get('children'):
                    for child in folder['children']:
                        result += format_folder(child, level + 1)
                        
                return result
            
            # 处理所有根文件夹
            for folder in response.content:
                output += format_folder(folder)
            
            return ToolSuccessResult(output)
            """
            # 格式化输出
            return ToolSuccessResult(response.content)
            
        except Exception as e:
            Logger.error(f"读取项目结构异常: {str(e)}")
            return ToolErrorResult(f"Failed to read project structure: {str(e)}") 
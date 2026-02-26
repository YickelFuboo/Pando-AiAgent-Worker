from typing import Dict
import json
from app.logger import logger
from app.agents.sweagent.model import ProjectInfo
from app.context.codebase.codegraph.query import CodeGraphQuery
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult

class ReadFileSummaryTool(BaseTool):
    """读取文件摘要工具"""
    @property
    def name(self) -> str:
        return "read_file_summary"
        
    @property
    def description(self) -> str:
        return """本工具用于代码Agent场景，通过本命令读取指定路径的代码文件重点额主要内容摘要，包含：文件中类定义签名、函数/方法定义签名等。当你需读取源码文件中主要内容，用于确定哪些类/结构/函数/方法可能与用户需求相关可能需要改时，可以调用本工具获取代码文件主要内容摘要，以进步一确定下一步哪些类/结构体/函数/方法源码可能需要修改，然后进一步通过其他获取类/结构体/函数/方法源码源代码，在源码基础上进行修改。本工具用于代码Agent场景，通过本工具读取指定路径的代码文件重点额主要内容摘要，包含：文件中类、结构体、函数、方法等的签名定义、及其主要功能描述。该工具提供了对源代码文件内容摘要的见解，对理解源代码文件主要内容框架至关重要，方便智能体根据文件摘要匹配用户需求可能需要修改的类、结构体、函数、方法等。
当需读取源代码文件中主要内容，用于确定哪些类、结构体、函数、方法可能与用户需求相关时，可以调用本工具获取源代码文件主要内容摘要，初步确定哪些类、结构体、函数、方法可能与用户需求相关，然后进一步通过read_function_code、read_class_code等工具获取指定的类、结构体、函数、方法获取详细代码，在源码基础上进行增量修改。"""

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
                    "description": "文件相对路径（相对于项目根目录）"
                }
            },
            "required": ["project_info", "file_path"]
        }              
        
    async def execute(self, project_info: ProjectInfo, file_path: str, **kwargs) -> ToolResult:
        """Execute file summary reading
        
        Args:
            file_path: Source file path
            
        Returns:
            ToolResult: Result containing file summary information
        """
        try:
            # 确保 project_info 是 ProjectInfo 实例
            if isinstance(project_info, dict):
                project_info = ProjectInfo(**project_info)
                
            if not project_info or not project_info.project_dir or not file_path:
                logger.error(f"params error: project_info={project_info}, file_path={file_path}")
                return ToolErrorResult("params error")   
            
            # file_path 调整为相对于 project_info.project_dir的路径
            # file_path = os.path.relpath(file_path, project_info.project_dir)

            # 查询文件摘要  
            with CodeGraphQuery() as query:
                response = await query.query_file_summary(
                    project_info=project_info,
                    file_paths=[file_path]
                )
            
            if not response.result:
                logger.warning(f"query file summary failed: {response.message}")
                return ToolErrorResult(response.message)
                
            if not response.content or not response.content['files'].get(file_path):
                logger.info(f"file {file_path} not found or not analyzed")
                return ToolErrorResult(f"file {file_path} not found or not analyzed")
                
            # 格式化输出
            file_info = response.content['files']
            """
            output = []
            
            # 基本信息
            output.append(f"File: {file_info['name']}")
            output.append(f"Language: {file_info['language']}")
            output.append(f"\nSummary:\n{file_info['summary']}")
            
            # 类信息
            if file_info['classes']:
                output.append("\nClasses:")
                for cls in file_info['classes']:
                    output.append(f"\n  {cls['name']}:")
                    output.append(f"    Summary: {cls['summary']}")
                    if cls['methods']:
                        output.append("    Methods:")
                        for method in cls['methods']:
                            output.append(f"      - {method['name']}: {method['summary']}")
            
            # 函数信息
            if file_info['functions']:
                output.append("\nFunctions:")
                for func in file_info['functions']:
                    output.append(f"  - {func['name']}: {func['summary']}")
  
            return ToolSuccessResult("\n".join(output))
        """
            # 格式化输出
            return ToolSuccessResult(file_info)
            
        except Exception as e:
            logger.error(f"Failed to read file summary: {str(e)}")
            return ToolErrorResult(f"Failed to read file summary: {str(e)}") 
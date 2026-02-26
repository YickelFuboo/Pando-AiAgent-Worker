from typing import Dict
import os
from app.logger import logger
from .base import BaseTool
from .schemes import ToolResult, ToolSuccessResult, ToolErrorResult


class ReplaceClassTool(BaseTool):
    """替换类工具"""  
    @property
    def name(self) -> str:
        return "replace_class"
    @property
    def description(self) -> str:
        return """对现有源码文件中的类或结构体的特定部分进行有针对性的修改，而不会覆盖整个文件、或覆盖完整类时。  
1. 如下情况下可以考虑使用本工具：
    - 小的、本地化的更改，如更新几行、函数实现、更改变量名、修改一段文本等。
    - 有针对性的改进，只需要更改文件中类或结构体代码段的特定部分。
    - 特别适用于长文件，其中大部分文件将保持不变。  
2. 使用注意事项：
    - 使用本工具前需要先获取需要修改的类或结构体现有内容。
    - 修改的内容中使用SEARCH/replace块替换现有Class的内容，这些块定义了对类或结构体的特定部分的确切更改。修改内容包含一个或多个SEARCH/REPLACE块，遵循以下确切格式：
  ```
  <<<<<<< SEARCH
  [exact content to find]
  =======
  [new content to replace with]
  >>>>>>> REPLACE
  ```
"""

    @property
    def parameters(self) -> Dict[str, Dict[str, str]]:
        return {
            "type": "object",
            "properties": {
            "file_path": {
                "type": "string",
                "description": "需要写入内容的文件的完整路径，请根据项目根目录信息拼装成完整的路径"
            },
            "class_name": {
                "type": "string",
                "description": "需要修改的Class名称"
            },
            "diff": {
                "type": "string",
                "description": """一个或多个SEARCH/REPLACE块，遵循以下确切格式：
  ```
  <<<<<<< SEARCH
  [exact content to find]
  =======
  [new content to replace with]
  >>>>>>> REPLACE
  ```
"""
                },
            },
            "required": ["file_path", "class_name", "diff"] 
        }              
    async def execute(self, file_path: str, class_name: str, diff: str, **kwargs) -> ToolResult:
        """Execute class content replacement
        
        Args:
            file_path: Target file path
            class_name: Class name to modify
            diff: Content with SEARCH/REPLACE blocks
            
        Returns:
            ToolResult: Result of the operation
        """
        try:
            if not file_path or not class_name or not diff:
                logger.error(f"Invalid parameters: file_path={file_path}, class_name={class_name}, diff={diff}")
                return ToolErrorResult("Invalid parameters")     
            
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return ToolErrorResult("File not found")
            """
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Parse SEARCH/REPLACE blocks
            blocks = diff.split('<<<<<<< SEARCH')
            if len(blocks) < 2:
                logger.error("No valid SEARCH/REPLACE blocks found")
                return ToolErrorResult("Invalid diff format: No SEARCH blocks found")
                
            # Process each SEARCH/REPLACE block
            for block in blocks[1:]:  # Skip first empty block
                try:
                    # Split SEARCH and REPLACE parts
                    search_replace = block.split('=======')
                    if len(search_replace) != 2:
                        continue
                        
                    search_content = search_replace[0].strip()
                    replace_part = search_replace[1].split('>>>>>>> REPLACE')
                    if len(replace_part) != 2:
                        continue
                        
                    replace_content = replace_part[0].strip()
                    
                    # Execute replacement
                    if search_content in content:
                        content = content.replace(search_content, replace_content)
                        logger.info(f"Successfully replaced content block in class {class_name}: {search_content[:50]}...")
                    else:
                        logger.warning(f"Content not found in class {class_name}: {search_content[:50]}...")
                except Exception as e:
                    logger.error(f"Error processing SEARCH/REPLACE block for class {class_name}: {str(e)}")
                    continue
            
            # Write file using r+ mode
            with open(file_path, 'r+', encoding='utf-8') as f:
                f.seek(0)
                f.truncate()
                f.write(content)
            """
            logger.info(f"Successfully updated class {class_name} in file {file_path}")
            return ToolSuccessResult(f"Successfully updated class {class_name}")
            
        except Exception as e:
            logger.error(f"Failed to replace class content: {str(e)}")
            return ToolErrorResult(f"Failed to replace class content: {str(e)}") 
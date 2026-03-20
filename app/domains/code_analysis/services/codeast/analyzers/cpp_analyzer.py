import re
import os
import logging
from tree_sitter import Language, Parser
from typing import Optional, List
from .base import LanguageAnalyzer
from ...models.model import FileInfo, FunctionInfo, ClassInfo, FunctionType, ClassType, Language as Lang

# 全局变量存储已加载的语言
LANGUAGES = {}

def get_language():
    """获取或初始化 C++ 语言解析器"""
    if 'cpp' not in LANGUAGES:
        try:
            # 构建语言库
            Language.build_library(
                'build/my-languages.so',
                [
                    'vendor/tree-sitter-cpp'
                ]
            )
            # 加载语言
            LANGUAGES['cpp'] = Parser()
            LANGUAGES['cpp'].set_language(
                Language.load('build/my-languages.so')
            )
        except Exception as e:
            logging.error(f"Error loading C++ language: {str(e)}")
            return None
    return LANGUAGES['cpp']

class CppAnalyzer(LanguageAnalyzer):
    def __init__(self, base_path: str, file_path: str):
        """初始化C++分析器"""
        super().__init__(base_path, file_path)        
        # 获取解析器
        self.parser = get_language()
    
    async def analyze_file(self) -> Optional[FileInfo]:
        """分析C++文件"""    
        if self.parser is None:
            logging.error(f"CPP parser is not initialized")
            return None

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = self.parser.parse(bytes(content, 'utf8'))
            if not tree:
                return None
                
            functions = []
            classes = []
            
            # 遍历语法树
            cursor = tree.walk()
            
            async def visit_node(node):
                if node.type == 'function_definition':
                    func_name = self._get_function_name(node)
                    if not func_name.startswith('_'):
                        func_node = await self._create_function_node(node, content)
                        if func_node:
                            functions.append(func_node)
                elif node.type == 'class_definition':
                    class_node = await self._create_class_node(node, content)
                    if class_node:
                        classes.append(class_node)
                
                for child in node.children:
                    await visit_node(child)
            
            await visit_node(tree.root_node)
            
            return FileInfo(
                name=os.path.basename(self.file_path),
                file_path=os.path.relpath(self.file_path, self.base_path),
                language=Lang.CPP,
                summary="",
                functions=functions,
                classes=classes,
                imports=self.get_imports(content, tree)
            )
        except Exception as e:
            logging.error(f"Error analyzing C++ file {self.file_path}: {str(e)}")
            return None
    
    def get_imports(self, content: str) -> List[str]:
        """获取C++文件的导入依赖"""
        imports = []
        include_pattern = r'#include\s*[<"]([^>"]+)[>"]'
        for match in re.finditer(include_pattern, content):
            imports.append(match.group(1))
        return imports
        
    def _get_function_name(self, node) -> str:
        """获取函数名"""
        for child in node.children:
            if child.type == 'identifier':
                return child.text.decode('utf8')
        return ''
        
    async def _create_function_node(self, node, content: str) -> Optional[FunctionInfo]:
        """创建函数节点"""
        func_name = self._get_function_name(node)
        if not func_name:
            return None
            
        source_code = content[node.start_byte:node.end_byte]
        
        signature = self._get_function_signature(node, content)
        full_name = func_name  # C++ 函数可能需要命名空间，这里简化处理
        
        return FunctionInfo(
            name=func_name,
            full_name=full_name,
            signature=signature,
            type=FunctionType.FUNCTION.value,
            file_path=os.path.relpath(self.file_path, self.base_path),
            source_code=source_code,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            params=self._get_function_params(node),
            param_types=self._get_param_types(node),
            returns=self._get_function_returns(node),
            return_types=self._get_return_types(node),
            docstring=self._get_comment(node, content)
        )
        
    async def _create_class_node(self, node, content: str) -> Optional[ClassInfo]:
        """创建类节点"""
        class_name = self._get_class_name(node)
        if not class_name:
            return None
            
        source_code = content[node.start_byte:node.end_byte]
        full_name = class_name  # C++ 类可能需要命名空间，这里简化处理
        
        return ClassInfo(
            name=class_name,
            full_name=full_name,
            file_path=os.path.relpath(self.file_path, self.base_path),
            node_type=ClassType.CLASS.value,
            source_code=source_code,
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            methods=await self._get_class_methods(node, content),
            attributes=self._get_class_attributes(node),
            docstring=self._get_comment(node, content)
        ) 
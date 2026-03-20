import os
import javalang
import logging
from typing import Optional, List
from .base import LanguageAnalyzer
from ...models.model import FileInfo, FunctionInfo, ClassInfo, ClassType, FunctionType, Language as Lang


class JavaAnalyzer(LanguageAnalyzer):
    def __init__(self, base_path: str, file_path: str):
        """初始化Java分析器"""
        super().__init__(base_path, file_path)
    
    async def analyze_file(self) -> Optional[FileInfo]:
        """分析Java文件"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = javalang.parse.parse(content)
            if not tree:
                raise Exception(f"Failed to parse Java file: {self.file_path}")
                
            functions = []
            classes = []
            
            # 分析Java类和方法
            for path, node in tree.filter(javalang.tree.ClassDeclaration):
                class_node = await self._create_class_node(node, content)
                if class_node:
                    classes.append(class_node)
            
            return FileInfo(
                name=os.path.basename(self.file_path),
                file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
                language=Lang.JAVA,
                summary="",
                functions=functions,
                classes=classes,
                imports=self.get_imports(content)
            )

        except Exception as e:
            logging.error(f"Error analyzing Java file {self.file_path}: {str(e)}")
            return None
        
    def get_imports(self, content: str) -> List[str]:
        """获取Java文件的导入依赖"""
        imports = []
        try:
            tree = javalang.parse.parse(content)
            for path, node in tree.filter(javalang.tree.Import):
                imports.append(node.path)
        except:
            pass
        return imports

    async def _create_class_node(self, node, content: str) -> Optional[ClassInfo]:
        """创建类节点"""
        methods = []
        for method in node.methods:
            if not method.name.startswith('_'):
                method_node = await self._create_method_node(method, content)
                if method_node:
                    methods.append(method_node)
        
        # 获取类的源代码
        lines = content.split('\n')
        start_line = node.position.line - 1 if node.position else 0
        # 计算结束行：找到最后一个方法的结束行，或者使用类的最后一个可见字符的行
        end_line = start_line
        if methods:
            end_line = max(m.end_line for m in methods if m.end_line) if methods else start_line
        else:
            # 如果没有方法，尝试找到类的结束大括号
            for i in range(start_line, len(lines)):
                if '}' in lines[i] and lines[i].strip().startswith('}'):
                    end_line = i + 1
                    break
        
        source_code = '\n'.join(lines[start_line:end_line]) if start_line < len(lines) else ""
        
        # 构建完整类名
        package_name = ""
        try:
            tree = javalang.parse.parse(content)
            for path, pkg_node in tree.filter(javalang.tree.PackageDeclaration):
                package_name = pkg_node.name
                break
        except:
            pass
        
        full_name = f"{package_name}.{node.name}" if package_name else node.name
        
        return ClassInfo(
            file_path=os.path.relpath(self.file_path, self.base_path),
            name=node.name,
            full_name=full_name,
            node_type=ClassType.CLASS.value,
            source_code=source_code,
            start_line=start_line + 1,
            end_line=end_line,
            methods=methods,
            attributes=self._get_class_attributes(node),
            docstring=self._get_comment(node)
        )

    async def _create_method_node(self, node, content: str) -> Optional[FunctionInfo]:
        """创建方法节点"""
        lines = content.split('\n')
        start_line = node.position.line - 1 if node.position else 0
        # 估算结束行：从开始行查找结束大括号
        end_line = start_line
        brace_count = 0
        for i in range(start_line, min(start_line + 100, len(lines))):  # 限制搜索范围
            line = lines[i]
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0 and i > start_line:
                end_line = i + 1
                break
        else:
            end_line = min(start_line + 10, len(lines))  # 如果找不到，使用默认值
        
        source_code = '\n'.join(lines[start_line:end_line]) if start_line < len(lines) else ""
        
        # 构建完整方法名
        package_name = ""
        class_name = ""
        try:
            tree = javalang.parse.parse(content)
            for path, pkg_node in tree.filter(javalang.tree.PackageDeclaration):
                package_name = pkg_node.name
                break
            for path, cls_node in tree.filter(javalang.tree.ClassDeclaration):
                if node in cls_node.methods:
                    class_name = cls_node.name
                    break
        except:
            pass
        
        full_name = f"{package_name}.{class_name}.{node.name}" if package_name and class_name else (f"{class_name}.{node.name}" if class_name else node.name)
        signature = self._get_method_signature(node)
        
        return FunctionInfo(
            name=node.name,
            full_name=full_name,
            signature=signature,
            type=FunctionType.METHOD.value,
            file_path=os.path.relpath(self.file_path, self.base_path),
            source_code=source_code,
            start_line=start_line + 1,
            end_line=end_line,
            params=self._get_method_params(node),
            param_types=self._get_param_types(node),
            returns=self._get_method_returns(node),
            return_types=self._get_return_types(node),
            docstring=self._get_comment(node)
        )
    
    def _get_method_signature(self, node) -> str:
        """获取方法签名 - 只包含类型，不包含参数名"""
        param_types = []
        for param in node.parameters:
            param_type = param.type.name if param.type else "Object"
            param_types.append(param_type)
        
        return_type = node.return_type.name if (node.return_type and hasattr(node.return_type, 'name')) else "void"
        param_signature = ", ".join(param_types)
        return f"{node.name}({param_signature}) -> {return_type}"
    
    def _get_method_params(self, node) -> List[str]:
        """获取方法参数名列表"""
        return [p.name for p in node.parameters]
    
    def _get_param_types(self, node) -> List[str]:
        """获取方法参数类型列表"""
        return [p.type.name if p.type else "Object" for p in node.parameters]
    
    def _get_method_returns(self, node) -> List[str]:
        """获取方法返回值列表"""
        if node.return_type:
            return [node.return_type.name if hasattr(node.return_type, 'name') else str(node.return_type)]
        return ["void"]
    
    def _get_return_types(self, node) -> List[str]:
        """获取方法返回类型列表"""
        if node.return_type:
            return [node.return_type.name if hasattr(node.return_type, 'name') else str(node.return_type)]
        return ["void"]
    
    def _get_class_attributes(self, node) -> List[str]:
        """获取类属性列表"""
        attributes = []
        for field in node.fields:
            for declarator in field.declarators:
                attributes.append(declarator.name)
        return attributes
    
    def _get_comment(self, node) -> Optional[str]:
        """获取注释"""
        if hasattr(node, 'documentation') and node.documentation:
            return node.documentation
        return None 
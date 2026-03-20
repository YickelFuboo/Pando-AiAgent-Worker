import os
import ast
import logging
from typing import Optional, List
from .base import LanguageAnalyzer
from ...models.model import FileInfo, FunctionInfo, ClassInfo, CallInfo, ClassType, FunctionType, Language as Lang


class PythonAnalyzer(LanguageAnalyzer):
    def __init__(self, base_path: str, file_path: str):
        """初始化Python分析器"""
        super().__init__(base_path, file_path)

    async def analyze_file(self) -> Optional[FileInfo]:
        """分析Python文件内容"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            # 先分析导入
            imports_map = self._analyze_imports(tree)
            
            # 分别存储顶层函数和类
            functions = []
            classes = []
            
            # 记录类方法的集合，用于后续过滤顶层函数
            class_methods = set()
            
            # 第一次遍历：处理类定义和收集类方法
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 分析类
                    class_node, methods = await self.analyze_class(node, imports_map)                    
                    classes.append(class_node)
                    class_methods.update(methods)  # 使用 update 而不是 add

            # 第二次遍历：只处理不在类中的函数
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node not in class_methods:
                        functions.append(await self.analyze_function(node, imports_map))
            
            # 创建文件节点，统一使用正斜杠
            return FileInfo(
                name=os.path.basename(self.file_path),
                file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
                language=Lang.PYTHON,
                summary="",
                functions=functions,
                classes=classes,
                imports=list(imports_map.values())
            )
            
        except Exception as e:
            logging.error(f"Error analyzing file {self.file_path}: {str(e)}")
            logging.error(f"Error type: {type(e)}")
            return None

    def _analyze_imports(self, tree: ast.AST) -> dict:
        """获取Python文件的导入依赖，将相对导入转换为项目内的绝对路径
        
        Args:
            tree: 已解析的AST
            
        Returns:
            dict: 导入映射 {local_name: full_path}
            
        Examples:
            对于文件 app/models/user.py:
            from ..utils import helper -> app.utils.helper
            from .base import Model -> app.models.base
            from app.config import settings -> app.config.settings
        """
        imports = {}
        
        # 获取当前模块的路径
        current_module = self._get_module_path()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                level = node.level  # 相对导入的层级数
                
                if level > 0:
                    # 处理相对导入
                    current_parts = current_module.split('.')
                    if len(current_parts) < level:
                        # 相对导入超出了项目根目录，忽略
                        continue
                        
                    # 移除相应数量的路径部分
                    base_path = '.'.join(current_parts[:-level])
                    if module:
                        # 有模块名的情况：from ..utils import helper
                        full_module = f"{base_path}.{module}" if base_path else module
                    else:
                        # 没有模块名的情况：from .. import helper
                        full_module = base_path
                else:
                    # 绝对导入
                    full_module = module
                
                # 处理导入的具体名称
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    if full_module:
                        imports[local_name] = f"{full_module}.{alias.name}"
                    else:
                        imports[local_name] = alias.name
        
        return imports

    async def analyze_function(self, node, imports_map: dict, class_name: str = None) -> FunctionInfo:
        """分析Python函数"""
        source_code = ast.unparse(node)
        
        # 分析参数
        params = self._get_function_params(node)
        param_types = []
        for arg in node.args.args:
            if arg.annotation:
                param_types.append(ast.unparse(arg.annotation))
            else:
                param_types.append("Any")
        
        # 分析返回值
        returns = self._get_function_returns(node)
        return_types = []
        if node.returns:
            return_types.append(ast.unparse(node.returns))
        else:
            return_types.append("Any")
        
        # 生成完整路径（模块路径+函数名）
        module_path = self._get_module_path()
        full_name = f"{module_path}.{node.name}"
        
        # 生成函数签名（函数名+参数类型+返回类型）
        # 只包含参数类型，不包含参数名，避免参数名不同但类型相同的函数被认为是不同的签名
        param_signature = ", ".join(param_types)
        return_type_str = return_types[0] if return_types else "Any"
        signature = f"{node.name}({param_signature}) -> {return_type_str}"
        
        # 分析函数调用，传入导入映射和类名（如果是类方法）
        calls = await self._get_function_calls(node, imports_map, module_path, class_name)
         
        return FunctionInfo(
            name=node.name,
            full_name=full_name,  # 包含完整路径的函数名
            signature=signature,  # 只包含函数签名信息
            type=FunctionType.FUNCTION.value,
            file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
            source_code=source_code,
            start_line=node.lineno,
            end_line=node.end_lineno,
            params=params,
            param_types=param_types,
            returns=returns,
            return_types=return_types,
            docstring=ast.get_docstring(node),
            calls=calls
        )
        
    async def _get_function_calls(self, node, imports_map: dict, module_path: str, class_name: str = None) -> List[CallInfo]:
        """分析函数调用
        
        Args:
            node: 函数节点
            imports_map: 导入映射
            module_path: 当前模块路径
            
        Returns:
            List[CallInfo]: 调用信息列表
        """
        # Python内置函数列表
        BUILTIN_FUNCTIONS = {
            'len', 'str', 'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple',
            'print', 'range', 'enumerate', 'zip', 'map', 'filter', 'sorted',
            'min', 'max', 'sum', 'any', 'all', 'abs', 'round', 'pow', 'divmod',
            'isinstance', 'issubclass', 'hasattr', 'getattr', 'setattr', 'delattr',
            'id', 'hash', 'type', 'super', 'next', 'iter', 'reversed','strip'
        }
        
        calls = []

        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    # 普通函数调用
                    name = n.func.id
                    if name in imports_map:
                        # 导入的函数调用
                        full_name = imports_map[name]
                        func_name = full_name.split('.')[-1]  # 使用原始函数名
                        calls.append(CallInfo(
                            name=func_name,
                            full_name=full_name,
                            signature=self._build_call_signature(n, func_name)
                        ))
                    else:
                        # 同模块的函数调用
                        if name in BUILTIN_FUNCTIONS:
                            continue

                        full_name = f"{module_path}.{name}"
                        calls.append(CallInfo(
                            name=name,
                            full_name=full_name,
                            signature=self._build_call_signature(n, name)
                        ))                
                elif isinstance(n.func, ast.Attribute):
                    if isinstance(n.func.value, ast.Name):
                        func_name = n.func.attr
                        value_name = n.func.value.id
                        if value_name == "self":
                            # 类方法调用
                            if class_name:
                                full_name = f"{module_path}.{class_name}.{func_name}"
                                calls.append(CallInfo(
                                    name=func_name,
                                    full_name=full_name,
                                    signature=self._build_call_signature(n, func_name)
                                ))
                        else:
                            # 检查是否是导入的模块
                            if value_name in imports_map:
                                base_path = imports_map[value_name]
                                full_name = f"{base_path}.{func_name}"
                                calls.append(CallInfo(
                                    name=func_name,
                                    full_name=full_name,
                                    signature=self._build_call_signature(n, func_name)
                                ))
                            else:
                                # 本地类的方法调用
                                full_name = f"{module_path}.{value_name}.{func_name}"
                                calls.append(CallInfo(
                                    name=func_name,
                                    full_name=full_name,
                                    signature=self._build_call_signature(n, func_name)
                                ))
                    elif isinstance(n.func.value, ast.Attribute):
                        # 处理多级调用，如 os.path.join
                        parts = []
                        value = n.func.value
                        while isinstance(value, ast.Attribute):
                            parts.insert(0, value.attr)
                            value = value.value
                        if isinstance(value, ast.Name):
                            base_name = value.id
                            if base_name in imports_map:
                                # 使用导入映射替换基础路径
                                base_path = imports_map[base_name]
                                parts.insert(0, base_path)
                            else:
                                parts.insert(0, base_name)
                            
                            full_path = '.'.join(parts + [n.func.attr])
                            func_name = n.func.attr
                            calls.append(CallInfo(
                                name=func_name,
                                full_name=full_path,
                                signature=self._build_call_signature(n, func_name)
                            ))
        
        return calls

    def _build_call_signature(self, node: ast.Call, func_name: str = None) -> str:
        """构建函数调用签名
        
        Args:
            node: 函数调用节点
            func_name: 已解析的函数名，如果为None则从node中解析
            
        Returns:
            str: 函数签名，格式: "func_name(param_types)->return_type"
            
        Examples:
            process_data(List[str], int) -> Dict
            save(self, data: Dict) -> bool
        """
        # 如果没有传入函数名，则从节点解析
        if func_name is None:
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            else:  # ast.Name
                func_name = node.func.id
        
        # 收集所有参数类型
        arg_types = []
        
        # 处理位置参数
        for arg in node.args:
            if isinstance(arg, ast.Constant):
                arg_types.append(type(arg.value).__name__)
            elif isinstance(arg, ast.Name):
                # 尝试从变量定义或类型注解获取类型
                arg_types.append(self._get_var_type(arg) or 'Any')
            elif isinstance(arg, ast.Call):
                # 函数调用的返回类型
                arg_types.append(self._get_call_return_type(arg) or 'Any')
            else:
                arg_types.append('Any')
        
        # 处理关键字参数
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Constant):
                arg_types.append(f"{keyword.arg}:{type(keyword.value.value).__name__}")
            elif isinstance(keyword.value, ast.Name):
                arg_type = self._get_var_type(keyword.value) or 'Any'
                arg_types.append(f"{keyword.arg}:{arg_type}")
            else:
                arg_types.append(f"{keyword.arg}:Any")
        
        # 获取返回类型（如果可能）
        return_type = self._get_call_return_type(node) or 'Any'
        
        return f"{func_name}({','.join(arg_types)})->{return_type}"

    def _get_var_type(self, node: ast.Name) -> Optional[str]:
        """尝试获取变量的类型"""
        # 这里可以实现更复杂的类型推断
        # 当前简单返回 None，后续可以扩展
        return None

    def _get_call_return_type(self, node: ast.Call) -> Optional[str]:
        """尝试获取函数调用的返回类型"""
        # 这里可以实现更复杂的返回类型推断
        # 当前简单返回 None，后续可以扩展
        return None

    async def analyze_class(self, node: ast.ClassDef, imports_map: dict) -> ClassInfo:
        """分析Python类"""
        source_code = ast.unparse(node)
        
        # 获取当前模块路径
        module_path = self._get_module_path()
        
        # 生成完整类名
        full_name = f"{module_path}.{node.name}"

        # 确定类的类型
        node_type = ClassType.CLASS  # 默认为普通类
        # 检查是否是接口/抽象类
        if any(base.id == 'ABC' for base in node.bases if isinstance(base, ast.Name)):
            node_type = ClassType.INTERFACE
        
        # 分析父类
        base_classes = self._get_base_classes(node, imports_map, module_path)
        
        methods = []
        attributes = []
        # 记录类方法的集合，用于后续过滤顶层函数
        class_methods = set()
        
        # 分析类成员
        for item in node.body:
            # 处理所有类型的方法定义
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 记录类方法，用于后续过滤顶层函数
                class_methods.add(item)

                method = await self.analyze_function(item, imports_map, class_name=node.name)
                # 转换为方法类型
                method.type = FunctionType.METHOD.value
                method.class_name = node.name
                # 更新方法的完整名称，使用类的完整名称
                method.full_name = f"{full_name}.{method.name}"
                methods.append(method)
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name):
                    attributes.append(item.target.id)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)
        
        class_info = ClassInfo(
            file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
            name=node.name,
            full_name=full_name,
            node_type=node_type.value,
            source_code=source_code,
            start_line=node.lineno,
            end_line=node.end_lineno,
            methods=methods,
            attributes=attributes,
            base_classes=base_classes,
            docstring=ast.get_docstring(node)
        )

        return class_info, class_methods

    def _get_base_classes(self, node: ast.ClassDef, imports_map: dict, module_path: str) -> List[ClassInfo]:
        """获取类的父类列表
        
        处理两种基类引用情况：
        1. 通过 import 导入并可能重命名的基类
           例如：from app.base import BaseClass as Base
                class MyClass(Base): ...
        
        2. 直接使用多级引用的基类
           例如：class MyClass(app.base.BaseClass): ...
        """
        base_classes = []
        
        for base in node.bases:
            if isinstance(base, ast.Name):
                # 跳过内置类型和特殊类型
                if base.id in ("object", "ABC", "Protocol"):
                    continue
                    
                # 情况1：处理可能通过 import 重命名的基类
                # 从 imports_map 中查找完整路径，如果没有则假设在当前模块
                base_full_name = imports_map.get(base.id, f"{module_path}.{base.id}")
                # 从完整路径中提取实际的类名
                base_name = base_full_name.split('.')[-1]
                
                base_classes.append(ClassInfo(
                    file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
                    name=base_name,
                    full_name=base_full_name,
                    node_type=ClassType.CLASS.value
                ))
            
            elif isinstance(base, ast.Attribute):
                # 情况2：处理多级引用的基类
                # 使用 ast.unparse 获取完整的引用路径
                base_full_name = ast.unparse(base)
                
                # 如果是通过 import as 重命名的模块中的类
                # 例如：import app.base as base_module
                #      class MyClass(base_module.BaseClass): ...
                if isinstance(base.value, ast.Name) and base.value.id in imports_map:
                    module_prefix = imports_map[base.value.id]
                    base_full_name = f"{module_prefix}.{base.attr}"
                
                # 从完整路径中提取实际的类名
                base_name = base_full_name.split('.')[-1]
                
                base_classes.append(ClassInfo(
                    file_path=os.path.relpath(self.file_path, self.base_path).replace('\\', '/'),
                    name=base_name,
                    full_name=base_full_name,
                    node_type=ClassType.CLASS.value
                ))
        
        return base_classes

    def _get_function_params(self, node) -> List[str]:
        """获取函数参数列表
        
        Args:
            node: 函数定义节点
            
        Returns:
            参数名列表，包括位置参数、默认参数、*args和**kwargs
        """
        params = []
        
        # 处理位置参数和默认参数
        for arg in node.args.args:
            params.append(arg.arg)
        
        # 处理 *args
        if node.args.vararg:
            params.append(f"*{node.args.vararg.arg}")
        
        # 处理关键字参数
        for arg in node.args.kwonlyargs:
            params.append(arg.arg)
        
        # 处理 **kwargs
        if node.args.kwarg:
            params.append(f"**{node.args.kwarg.arg}")
        
        return params

    def _get_function_returns(self, node) -> List[str]:
        """获取函数返回值列表
        
        Args:
            node: 函数定义节点
            
        Returns:
            返回值列表。通过分析:
            1. return 语句
            2. yield 语句
            3. 返回值类型注解
        """
        returns = []
        
        # 分析 return 语句
        for n in ast.walk(node):
            if isinstance(n, ast.Return) and n.value:
                if isinstance(n.value, ast.Name):
                    returns.append(n.value.id)
                elif isinstance(n.value, ast.Constant):
                    returns.append(type(n.value.value).__name__)
                elif isinstance(n.value, ast.Call):
                    if isinstance(n.value.func, ast.Name):
                        returns.append(n.value.func.id)
                    elif isinstance(n.value.func, ast.Attribute):
                        returns.append(n.value.func.attr)
                    
        # 分析 yield 语句
        for n in ast.walk(node):
            if isinstance(n, (ast.Yield, ast.YieldFrom)):
                returns.append("Generator")
                break
            
        # 分析返回值类型注解
        if node.returns:
            if isinstance(node.returns, ast.Name):
                returns.append(node.returns.id)
            elif isinstance(node.returns, ast.Constant):
                returns.append(str(node.returns.value))
            
        # 如果没有找到任何返回值信息
        if not returns:
            returns.append("None")
        
        return list(set(returns))  # 去重 


    def _get_module_path(self) -> str:
        """获取当前文件的模块路径
        
        Returns:
            str: 模块路径，例如: "app.models.user"
            
        Examples:
            文件路径: "E:/project/app/models/user.py"
            项目路径: "E:/project"
            返回: "app.models.user"
        """
        return os.path.splitext(os.path.relpath(self.file_path, self.base_path))[0].replace(os.sep, '.') 
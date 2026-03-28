import logging
import os
from dataclasses import asdict
from typing import Dict,List,Union,Optional
from neo4j import GraphDatabase
from app.utils.common import local_now_iso
from ..codeast.model import FileInfo,FunctionInfo,ClassInfo,FolderInfo,CallInfo


class Neo4jService:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()
        
    def save_project(self, repo_id: str, repo_name: str, repo_local_path: str):
        """创建或更新项目
        
        Args:
            repo_id: 仓库（项目）全局唯一标识符，与图谱中其他节点字段 repo_id 一致
            repo_name: 项目名称
            repo_local_path: 项目根路径
        """
        with self.driver.session() as session:
            try:
                # 1. 创建或更新项目节点
                session.run("""
                    MERGE (p:Project {repo_id: $repo_id})
                    SET p.name = $name,
                        p.root_path = $root_path,
                        p.updated_at = datetime($updated_at)
                    WITH p
                    WHERE p.created_at IS NULL
                    SET p.created_at = datetime($updated_at)
                    RETURN p
                """, {
                    'repo_id': repo_id,
                    'name': repo_name,
                    'root_path': repo_local_path,
                    'updated_at': local_now_iso(),
                })
            
            except Exception as e:
                logging.error(f"Error in save_project: {str(e)}, repo_id: {repo_id}, name: {repo_name}")
                logging.error(f"Error type: {type(e)}")
                raise
    
    def save_folder_node(self, repo_id: str, folder_node: FolderInfo, parent_folder_node: FolderInfo = None):
        """保存完整的文件夹结构
        1. 文件夹节点
        2. 根文件夹，Project=>(CONTAINS)=>文件夹节点
        3. 子文件夹节点
        4. 子文件夹：文件夹=>(CONTAINS)=>子文件夹、子文件
        5. 文件节点每分析一个就会保存一个，避免积累，这里仅更新文件节点与文件夹的关系"""
        if not folder_node:
            return
        
        with self.driver.session() as session:
            try:
                # 1. 保存文件夹节点
                session.run("""
                    MERGE (folder:Folder {
                        repo_id: $repo_id,
                        name: $name,
                        path: $path
                    })
                    SET folder.display_name = $name,
                        folder.updated_at = datetime($updated_at)
                    WITH folder
                    WHERE folder.created_at IS NULL
                    SET folder.created_at = datetime($updated_at)
                """, {
                    'repo_id': repo_id,
                    'name': folder_node.name,
                    'path': folder_node.path,
                    'updated_at': local_now_iso(),
                })

                # 如果存在父文件夹节点，则创建parent_folder_node与folder_node的关系
                # 否则，创建folder_node与Project的关系
                if parent_folder_node and parent_folder_node.name != "":
                    session.run("""
                        MATCH (parent:Folder {
                            repo_id: $repo_id,
                            name: $parent_name,
                            path: $parent_path
                        }) 
                        MATCH (child:Folder {
                            repo_id: $repo_id,
                            name: $child_name,
                            path: $child_path
                        })
                        MERGE (parent)-[:CONTAINS]->(child)
                    """, {
                        'repo_id': repo_id, 
                        'parent_name': parent_folder_node.name,
                        'parent_path': parent_folder_node.path,
                        'child_name': folder_node.name,
                        'child_path': folder_node.path
                    })  
                else:
                    session.run("""
                        MATCH (p:Project {repo_id: $repo_id})
                        MATCH (folder:Folder {
                            repo_id: $repo_id,
                            name: $name,
                            path: $path
                        })
                        MERGE (p)-[:CONTAINS]->(folder)
                    """, {
                        'repo_id': repo_id,
                        'name': folder_node.name,
                        'path': folder_node.path
                    })

                # 2. 递归处理子文件夹
                for subfolder in folder_node.subfolders:
                    # 先保存子文件夹
                    self.save_folder_node(repo_id, subfolder, folder_node)
            
                # 3. 保存文件节点及其内容
                for file in folder_node.files:
                    # 文件每次分析完毕后先保存，这里补充重复保存
                    self.save_file_node(repo_id, file)
                    self._update_folder_contains_file(repo_id, folder_node, file)
                
            except Exception as e:
                logging.error(f"Error in save_folder_node: {str(e)}, folder_node: {folder_node}")
                logging.error(f"Error type: {type(e)}")
                raise
    
    # 更新FolderNode与FileNode的关系
    def _update_folder_contains_file(self, repo_id: str, folder_node: FolderInfo, file_node: FileInfo):
        """更新FolderNode与FileNode的关系"""
        with self.driver.session() as session:
            try:
                # 创建文件夹与文件的关系
                session.run("""
                    MATCH (folder:Folder {
                        repo_id: $repo_id,
                        name: $folder_name,
                        path: $folder_path
                    })
                    MATCH (file:File {
                        repo_id: $repo_id,
                        name: $name,
                        file_path: $file_path
                    })
                    MERGE (folder)-[:CONTAINS]->(file)
                """, {
                    'repo_id': repo_id,
                    'folder_name': folder_node.name,
                    'folder_path': folder_node.path,
                    'name': file_node.name,
                    'file_path': file_node.file_path
                })
            except Exception as e:
                logging.error(f"Error in update_folder_contains_file: {str(e)}, folder_node: {folder_node}, file_node: {file_node}")
                logging.error(f"Error type: {type(e)}")
                raise

    def save_file_node(self, repo_id: str, file_node: FileInfo):
        """保存文件节点及其包含的函数和类"""
        with self.driver.session() as session:
            try:
                # 1. 创建 File 节点
                session.run("""
                    MERGE (f:File {
                        repo_id: $repo_id,
                        name: $name,
                        file_path: $file_path
                    })
                    SET f.language = $language,
                        f.imports = $imports,
                        f.display_name = $name,
                        f.updated_at = datetime($updated_at)
                    WITH f
                    WHERE f.created_at IS NULL
                    SET f.created_at = datetime($updated_at)
                    RETURN f
                """, {
                    'repo_id': repo_id,
                    'name': file_node.name,
                    'file_path': file_node.file_path,
                    'language': file_node.language,
                    'imports': file_node.imports,
                    'updated_at': local_now_iso(),
                })

                # 2. 保存文件中的类和函数节点            
                if file_node.classes:
                    for class_node in file_node.classes:
                        if isinstance(class_node, ClassInfo):
                            self.save_class_node(repo_id, file_node, class_node)
                        else:
                            logging.warning(f"Invalid class node type: {type(class_node)}")
                        
                if file_node.functions:
                    for func_node in file_node.functions:
                        if isinstance(func_node, FunctionInfo):
                            self.save_function_node(repo_id, file_node, func_node)
                        else:
                            logging.warning(f"Invalid function node type: {type(func_node)}")

            except Exception as e:
                logging.error(f"Error in save_file_node: {str(e)}")
                logging.error(f"Error type: {type(e)}")
                logging.error(f"File node: {file_node}")
                raise
    
    def save_class_node(self, repo_id: str, file_node: FileInfo, class_node: ClassInfo):
        """保存类节点及其方法"""
        with self.driver.session() as session:
            try:                
                # 1. 创建 Class 节点                
                class_data = asdict(class_node)
                session.run("""
                    MERGE (c:Class {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name
                    })
                    SET c.file_path = $file_path,
                        c.node_type = $node_type,
                        c.docstring = $docstring,
                        c.source_code = $source_code,
                        c.attributes = $attributes,
                        c.display_name = $name,
                        c.updated_at = datetime($updated_at)
                    WITH c
                    WHERE c.created_at IS NULL
                    SET c.created_at = datetime($updated_at)
                    RETURN c
                """, {
                    'repo_id': repo_id,
                    'file_path': file_node.file_path,
                    'updated_at': local_now_iso(),
                    **class_data
                })
                
                # 2. 建立与文件的关系
                session.run("""
                    MATCH (f:File {repo_id: $repo_id, name: $file_name, file_path: $file_path})
                    MATCH (c:Class {repo_id: $repo_id, name: $class_name, full_name: $class_full_name})
                    MERGE (f)-[:CONTAINS]->(c)
                """, {
                    'repo_id': repo_id,
                    'file_name': file_node.name,
                    'file_path': file_node.file_path,
                    'class_name': class_node.name,
                    'class_full_name': class_node.full_name
                })

                # 3. 处理继承关系（如果有）
                if class_node.base_classes:
                    self._save_class_inheritance(repo_id, class_node)
                
                # 4. 处理类方法
                if class_node.methods:
                    for method_node in class_node.methods:
                        if isinstance(method_node, FunctionInfo):
                            self.save_method_node(repo_id, class_node, method_node)
                        else:
                            logging.warning(f"Invalid method node type: {type(method_node)}")    
                
            except Exception as e:
                logging.error(f"Error in save_class_node: {str(e)}")
                logging.error(f"Error type: {type(e)}")
                logging.error(f"File path: {file_node.file_path}")
                logging.error(f"Class node: {class_node}")
                raise

    def _save_class_inheritance(self, repo_id: str, class_node: ClassInfo):
        """处理类的继承关系
        
        Args:
            repo_id: 项目ID
            class_node: 类节点
        """
        with self.driver.session() as session:
            try:
                session.run("""
                    MATCH (c:Class {repo_id: $repo_id, name: $name, full_name: $full_name})
                    UNWIND $base_classes as base
                    // 使用 MERGE 而不是 MATCH 来确保父类存在
                    MERGE (base_class:Class {
                        repo_id: $repo_id,
                        name: base.name,
                        full_name: base.full_name
                    })
                    // 设置父类的基本属性
                    ON CREATE SET 
                        base_class.node_type = base.node_type,
                        base_class.display_name = base.name,
                        base_class.created_at = datetime($updated_at)
                    SET base_class.updated_at = datetime($updated_at)
                    
                    WITH c, base_class, base_class.node_type = 'interface' as is_interface
                    FOREACH (x IN CASE WHEN is_interface THEN [1] ELSE [] END |
                        MERGE (c)-[:IMPLEMENTS]->(base_class)
                    )
                    FOREACH (x IN CASE WHEN NOT is_interface THEN [1] ELSE [] END |
                        MERGE (c)-[:INHERITS]->(base_class)
                    )
                """, {
                    'repo_id': repo_id,
                    'name': class_node.name,
                    'full_name': class_node.full_name,
                    'base_classes': asdict(class_node)['base_classes'],
                    'updated_at': local_now_iso(),
                })
                
            except Exception as e:
                logging.error(f"Error in _save_class_inheritance: {str(e)}")
                logging.error(f"Error type: {type(e)}")
                logging.error(f"Class node: {class_node}")
                raise
    
    def save_function_node(self, repo_id: str, file_node: FileInfo, function_node: FunctionInfo):
        """保存函数节点（包括普通函数和类方法）
        
        Args:
            repo_id: 项目ID
            file_node: 父节点（文件）
            function_node: 函数节点
            
        处理以下关系：
        1. File -(CONTAINS)-> Function (如果父节点是文件)
        2. Function -(CALLS)-> Function/Method/API (函数调用关系)
        """

        with self.driver.session() as session:
            try:
                # 1. 创建 Function 节点
                function_data = asdict(function_node)
                session.run("""
                    MERGE (f:Function {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name,
                        signature: $signature
                    })
                    SET f.file_path = $file_path,
                        f.source_code = $source_code,
                        f.docstring = $docstring,
                        f.params = $params,
                        f.param_types = $param_types,
                        f.returns = $returns,
                        f.return_types = $return_types,
                        f.class_name = $class_name,
                        f.display_name = $name,
                        f.updated_at = datetime($updated_at)
                    WITH f
                    WHERE f.created_at IS NULL
                    SET f.created_at = datetime($updated_at)
                """, {
                    'repo_id': repo_id,
                    'file_path': file_node.file_path,
                    'class_name': '',
                    'parent_type': 'File',
                    'updated_at': local_now_iso(),
                    **function_data
                })
                    
                # 2. 建立与父节点的关系
                session.run("""
                    MATCH (file:File {repo_id: $repo_id, name: $file_name, file_path: $file_path})
                    MATCH (f:Function {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name,
                        signature: $signature
                    }) 
                    MERGE (file)-[:CONTAINS]->(f)
                """, {
                    'repo_id': repo_id,
                    'file_name': file_node.name,
                    'file_path': file_node.file_path,
                    'name': function_node.name,
                    'full_name': function_node.full_name,
                    'signature': function_node.signature
                })
                
                # 3. 处理函数调用关系
                if function_node.calls:
                    for call_info in function_node.calls:
                        self._save_function_calls(repo_id, function_node, call_info)
                        
            except Exception as e:
                logging.error(f"Error in save_function_node: {str(e)}, function_node: {function_node}")
                logging.error(f"Error type: {type(e)}")
                raise
                              
    def save_method_node(self, repo_id: str, class_node: ClassInfo, function_node: FunctionInfo):
        """保存函数节点（包括普通函数和类方法）
        
        Args:
            repo_id: 项目ID
            class_node: 父节点（类）
            function_node: 函数节点
            
        处理以下关系：
        1. File -(CONTAINS)-> Function (如果父节点是文件)
        2. Class -(CALLS)-> Method (函数调用关系)
        """

        with self.driver.session() as session:
            try:
                # 1. 创建 Function 节点
                function_data = asdict(function_node)
                session.run("""
                    MERGE (f:Function {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name,
                        signature: $signature
                    })
                    SET f.file_path = $file_path,
                        f.source_code = $source_code,
                        f.docstring = $docstring,
                        f.params = $params,
                        f.param_types = $param_types,
                        f.returns = $returns,
                        f.return_types = $return_types,
                        f.class_name = $class_name,
                        f.display_name = $name,
                        f.updated_at = datetime($updated_at)
                    WITH f
                    WHERE f.created_at IS NULL
                    SET f.created_at = datetime($updated_at)
                """, {
                    'repo_id': repo_id,
                    'file_path': class_node.file_path,
                    'class_name': class_node.name, 
                    'parent_type': 'Class',
                    'updated_at': local_now_iso(),
                    **function_data
                })
                    
                # 2. 建立与父节点的关系
                session.run("""
                    MATCH (c:Class {repo_id: $repo_id, name: $class_name, full_name: $class_full_name})
                    MATCH (f:Function {
                        repo_id: $repo_id,
                        name: $name,
                        full_name: $full_name,
                        signature: $signature
                    }) 
                    MERGE (c)-[:CONTAINS]->(f)
                """, {
                    'repo_id': repo_id,
                    'class_name': class_node.name,
                    'class_full_name': class_node.full_name,
                    'name': function_node.name,
                    'full_name': function_node.full_name,
                    'signature': function_node.signature
                })
                
                # 3. 处理函数调用关系
                if function_node.calls:
                    for call_info in function_node.calls:
                        self._save_function_calls(repo_id, function_node, call_info)
                        
            except Exception as e:
                logging.error(f"Error in save_method_node: {str(e)}, function_node: {function_node}")
                logging.error(f"Error type: {type(e)}")
                raise
    
    def _save_function_calls(self, repo_id: str, function_node: FunctionInfo, call_info: CallInfo):
        """保存函数的调用关系"""
        with self.driver.session() as session:
            try:
                session.run("""
                    // 找到调用方函数
                    MATCH (caller:Function {
                        repo_id: $repo_id,
                        name: $caller_name,
                        full_name: $caller_full_name,
                        signature: $caller_signature
                    })
                    
                    // 找到被调用方（可能是函数、方法或API），找不到先按照API方式创建
                    MERGE (callee:Function {
                        repo_id: $repo_id,
                        name: $callee_name,
                        full_name: $callee_full_name,
                        signature: $callee_signature
                    })
                    ON CREATE SET
                        callee.node_type = 'api',
                        callee.created_at = datetime($updated_at)
                    SET callee.updated_at = datetime($updated_at)
                    
                    
                    // 创建调用关系
                    WITH caller, callee
                    MERGE (caller)-[r:CALLS]->(callee)
                """, {
                    'repo_id': repo_id,
                    'caller_name': function_node.name,
                    'caller_full_name': function_node.full_name,
                    'caller_signature': function_node.signature,
                    'callee_name': call_info.name,
                    'callee_full_name': call_info.full_name,
                    'callee_signature': call_info.signature,
                    'updated_at': local_now_iso(),
                })

            except Exception as e:
                logging.error(f"Error in _save_function_calls: {str(e)}, function_node: {function_node}, call_info: {call_info}")
                logging.error(f"Error type: {type(e)}")
                raise
    
    def delete_stale_nodes(self, repo_id: str, before_timestamp: str):
        """删除过期节点（未在最近更新中出现的节点）
        
        删除所有属于指定仓库且在指定时间之前未更新的节点及其关系
        """
        with self.driver.session() as session:
            try:
                session.run("""
                    MATCH (n)
                    WHERE n.repo_id = $repo_id 
                    AND n.updated_at < datetime($before_timestamp)
                    AND NOT n:Project  // 不删除项目节点
                    DETACH DELETE n
                """, {
                    'repo_id': repo_id,
                    'before_timestamp': before_timestamp
                }) 
            
            except Exception as e:
                logging.error(f"Error in delete_stale_nodes: {str(e)}, repo_id: {repo_id}, before_timestamp: {before_timestamp}")
                logging.error(f"Error type: {type(e)}")
                raise

    def delete_file_nodes(self, repo_id: str, file_path: str):
        """删除文件及其相关节点（函数、类等）
        
        用于文件更新或删除场景。
        DETACH DELETE 会自动处理：
        1. 文件中的节点（函数、类等）
        2. 其他文件对该文件的依赖关系
        3. 其他函数对该文件中函数的调用关系
        4. 其他类对该文件中类的继承关系
        5. 文件节点本身
        """
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                try:
                    tx.run("""
                        MATCH (f:File {
                            repo_id: $repo_id,
                            file_path: $file_path
                        })-[:CONTAINS]->(n)
                        DETACH DELETE n
                        
                        WITH f
                        DETACH DELETE f
                    """, {
                        'repo_id': repo_id,
                        'file_path': file_path
                    })
                    tx.commit()
                except Exception as e:
                    tx.rollback()
                    logging.error(f"Error in delete_file_nodes: {str(e)}, repo_id: {repo_id}, file_path: {file_path}")
                    logging.error(f"Error type: {type(e)}")
                    raise e

    def delete_folder_nodes(self, repo_id: str, folder_path: str):
        """删除文件夹及其所有子节点
        
        用于文件夹删除场景。会删除：
        1. 所有子文件夹（通过STARTS WITH匹配）
        2. 所有文件
        3. 文件中的所有函数（包括类方法）和类
        4. 相关的所有关系
        """
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                try:
                    tx.run("""
                        // 1. 匹配目标文件夹及其所有子文件夹
                        MATCH (folder:Folder {repo_id: $repo_id})
                        WHERE folder.path STARTS WITH $folder_path
                        
                        // 2. 匹配这些文件夹中的所有文件
                        OPTIONAL MATCH (folder)-[:CONTAINS]->(file:File)
                        
                        // 3. 匹配文件中的所有函数和类
                        OPTIONAL MATCH (file)-[:CONTAINS]->(node)
                        WHERE node:Function OR node:Class
                        
                        // 4. 删除所有相关节点（DETACH会删除所有关系）
                        WITH DISTINCT folder, file, node
                        DETACH DELETE node, file, folder
                    """, {
                        'repo_id': repo_id,
                        'folder_path': folder_path
                    })
                    tx.commit()
                except Exception as e:
                    tx.rollback()
                    logging.error(f"Error in delete_folder_nodes: {str(e)}, repo_id: {repo_id}, folder_path: {folder_path}")
                    logging.error(f"Error type: {type(e)}")
                    raise e

    def delete_repo_nodes(self, repo_id: str):
        """删除指定 repo_id 的全部图谱数据（包含 Project/Folder/File/Class/Function 等节点及其关系）。"""
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                try:
                    tx.run(
                        """
                        MATCH (n)
                        WHERE n.repo_id = $repo_id
                        DETACH DELETE n
                        """,
                        {"repo_id": repo_id},
                    )
                    tx.commit()
                except Exception as e:
                    tx.rollback()
                    logging.error("Error in delete_repo_nodes: %s, repo_id: %s", e, repo_id)
                    logging.error("Error type: %s", type(e))
                    raise

    def query_file_summary(self, repo_id: str, file_paths: List[str]) -> Dict:
        """查询文件内容概述"""
        with self.driver.session() as session:
            result = session.run("""
                // 1. 匹配文件节点
                MATCH (file:File)
                WHERE file.file_path IN $file_paths
                AND file.repo_id = $repo_id
                
                // 2. 查找文件中的类及其方法
                OPTIONAL MATCH (file)-[:CONTAINS]->(class:Class)
                OPTIONAL MATCH (class)-[:CONTAINS]->(method:Function)
                WITH file, class,
                     collect({
                         name: method.name,
                         signature: method.signature,
                         type: method.`type`
                     }) as methods
                
                // 3. 收集类信息
                WITH file,
                     collect({
                         name: class.name,
                         full_name: class.full_name,
                         methods: methods
                     }) as classes
                
                // 4. 查找顶层函数（不属于任何类）
                OPTIONAL MATCH (file)-[:CONTAINS]->(func:Function)
                WHERE NOT EXISTS {
                    MATCH (c:Class)-[:CONTAINS]->(func)
                }
                
                // 5. 返回完整信息
                RETURN file.file_path as path,
                       file.name as name,
                       file.language as language,
                       classes,
                       collect({
                           name: func.name,
                           signature: func.signature,
                           type: func.`type`
                       }) as functions
                ORDER BY file.file_path
            """, {
                'repo_id': repo_id,
                'file_paths': file_paths
            })
            
            return list(result)

    def query_dependents_of_file(self, repo_id: str, file_path: str) -> List[str]:
        """查询依赖本文件的其他文件列表（CALLS + 继承/实现）。"""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(fn:Function)
                MATCH (caller:Function)-[:CALLS]->(fn)
                WHERE caller.file_path IS NOT NULL AND caller.file_path <> $file_path
                RETURN DISTINCT caller.file_path AS other_file
                UNION
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(cl:Class)-[:CONTAINS]->(m:Function)
                MATCH (caller:Function)-[:CALLS]->(m)
                WHERE caller.file_path IS NOT NULL AND caller.file_path <> $file_path
                RETURN DISTINCT caller.file_path AS other_file
                UNION
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(base:Class)
                MATCH (sub:Class)-[:INHERITS|IMPLEMENTS]->(base)
                WHERE sub.file_path IS NOT NULL AND sub.file_path <> $file_path
                RETURN DISTINCT sub.file_path AS other_file
                """,
                {"repo_id": repo_id,"file_path": file_path},
            )
            return [record["other_file"] for record in result if record and record.get("other_file")]

    def query_dependented_of_file(self, repo_id: str, file_path: str) -> List[str]:
        """查询本文件依赖的其他文件列表（CALLS + 继承/实现）。"""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(fn:Function)
                MATCH (fn)-[:CALLS]->(callee:Function)
                WHERE callee.file_path IS NOT NULL AND callee.file_path <> $file_path
                RETURN DISTINCT callee.file_path AS other_file
                UNION
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(cl:Class)-[:CONTAINS]->(m:Function)
                MATCH (m)-[:CALLS]->(callee:Function)
                WHERE callee.file_path IS NOT NULL AND callee.file_path <> $file_path
                RETURN DISTINCT callee.file_path AS other_file
                UNION
                MATCH (target:File {repo_id: $repo_id,file_path: $file_path})
                MATCH (target)-[:CONTAINS]->(cl:Class)
                MATCH (cl)-[:INHERITS|IMPLEMENTS]->(base:Class)
                WHERE base.file_path IS NOT NULL AND base.file_path <> $file_path
                RETURN DISTINCT base.file_path AS other_file
                """,
                {"repo_id": repo_id,"file_path": file_path},
            )
            return [record["other_file"] for record in result if record and record.get("other_file")]

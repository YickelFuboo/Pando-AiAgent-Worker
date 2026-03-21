import logging
from typing import List,Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.code_analysis.service.codechunk.services.repo_functions_mgmt import RepoFunctionsMgmt
from app.domains.code_analysis.service.codechunk.services.repo_classes_mgmt import RepoClassesMgmt
from app.domains.code_analysis.service.codechunk.services.repo_chunks_mgmt import RepoCodeChunksMgmt
from app.domains.code_analysis.service.codechunk.schemes.scheme import CodeChunkCreate,CodeChunkUpdate,FunctionDataCreate,FunctionDataUpdate,ClassDataCreate,ClassDataUpdate
from app.domains.code_analysis.service.codeast.models.model import FunctionInfo,ClassInfo


class CodeChunker:
    """代码切片工具类 - 提供代码切片的便捷接口"""
    
    def __init__(self, db_session: AsyncSession, repo_id: str):
        self.db_session = db_session
        self.repo_id = repo_id
        self.function_db = RepoFunctionsMgmt(db_session, repo_id)
        self.class_db = RepoClassesMgmt(db_session, repo_id)
        self.chunk_db = RepoCodeChunksMgmt(db_session, repo_id)
    
    async def chunk_function(self, function_info: FunctionInfo, generate_summary: bool = False) -> Optional[str]:
        """对函数进行切片并存储
        
        Args:
            function_info: 函数信息
            generate_summary: 是否立即生成功能描述（默认False，后续通过batch_generate_summary批量处理）
            
        Returns:
            创建的记录ID
        """
        try:
            function_data = await self.function_db.create(FunctionDataCreate(
                repo_id=self.repo_id,
                source_code=function_info.source_code,
                file_path=function_info.file_path,
                start_line=function_info.start_line,
                end_line=function_info.end_line,
                function_name=function_info.name,
                function_signature=function_info.signature
            ))
            
            if generate_summary:
                summary = await self.function_db.generate_summary(function_data)
                if summary:
                    await self.function_db.update(function_data.id, FunctionDataUpdate(
                        summary=summary,
                        is_summarized=True
                    ))
            
            return function_data.id
        except Exception as e:
            logging.error(f"函数切片失败: {e}")
            return None
    
    async def chunk_class(self, class_info: ClassInfo, generate_summary: bool = False) -> Optional[str]:
        """对类进行切片并存储
        
        Args:
            class_info: 类信息
            generate_summary: 是否立即生成功能描述（默认False，后续通过batch_generate_summary批量处理）
            
        Returns:
            创建的记录ID
        """
        try:
            class_data = await self.class_db.create(ClassDataCreate(
                repo_id=self.repo_id,
                source_code=class_info.source_code,
                file_path=class_info.file_path,
                start_line=class_info.start_line,
                end_line=class_info.end_line,
                class_name=class_info.name,
                class_type=class_info.node_type
            ))
            
            if generate_summary:
                summary = await self.class_db.generate_summary(class_data)
                if summary:
                    await self.class_db.update(class_data.id, ClassDataUpdate(
                        summary=summary,
                        is_summarized=True
                    ))
            
            return class_data.id
        except Exception as e:
            logging.error(f"类切片失败: {e}")
            return None
    
    async def chunk_code_segment(self, source_code: str, file_path: str, 
                                start_line: int, end_line: int, generate_summary: bool = False) -> Optional[str]:
        """对代码片段进行切片并存储
        
        Args:
            source_code: 源码内容
            file_path: 文件路径
            start_line: 起始行号
            end_line: 结束行号
            generate_summary: 是否立即生成功能描述（默认False，后续通过batch_generate_summary批量处理）
            
        Returns:
            创建的记录ID
        """
        try:
            chunk = await self.chunk_db.create(CodeChunkCreate(
                repo_id=self.repo_id,
                source_code=source_code,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line
            ))
            
            if generate_summary:
                summary = await self.chunk_db.generate_summary(chunk)
                if summary:
                    await self.chunk_db.update(chunk.id, CodeChunkUpdate(
                        summary=summary,
                        is_summarized=True
                    ))
            
            return chunk.id
        except Exception as e:
            logging.error(f"代码片段切片失败: {e}")
            return None
    
    async def chunk_functions_from_source(self, source_code: str, file_path: str,
                                          functions: List[FunctionInfo], generate_summary: bool = False) -> List[str]:
        """从源码中提取函数并切片
        
        Args:
            source_code: 源码内容
            file_path: 文件路径
            functions: 函数信息列表
            generate_summary: 是否立即生成功能描述（默认False，后续通过batch_generate_summary批量处理）
            
        Returns:
            创建的记录ID列表
        """
        try:
            ids = []
            for func_info in functions:
                func_id = await self.chunk_function(func_info, generate_summary)
                if func_id:
                    ids.append(func_id)
            return ids
        except Exception as e:
            logging.error(f"批量函数切片失败: {e}")
            return []
    
    async def chunk_classes_from_source(self, source_code: str, file_path: str,
                                       classes: List[ClassInfo], generate_summary: bool = False) -> List[str]:
        """从源码中提取类并切片
        
        Args:
            source_code: 源码内容
            file_path: 文件路径
            classes: 类信息列表
            generate_summary: 是否立即生成功能描述（默认False，后续通过batch_generate_summary批量处理）
            
        Returns:
            创建的记录ID列表
        """
        try:
            ids = []
            for class_info in classes:
                class_id = await self.chunk_class(class_info, generate_summary)
                if class_id:
                    ids.append(class_id)
            return ids
        except Exception as e:
            logging.error(f"批量类切片失败: {e}")
            return []
    
    async def chunk_source_code(self, source_code: str, chunk_size: int = 500, 
                               overlap: int = 50) -> List[tuple]:
        """将源码按指定大小切片
        
        Args:
            source_code: 源码内容
            chunk_size: 切片大小（行数）
            overlap: 重叠行数
            
        Returns:
            [(start_line, end_line, code), ...] 列表
        """
        try:
            lines = source_code.split('\n')
            chunks = []
            start = 0
            
            while start < len(lines):
                end = min(start + chunk_size, len(lines))
                chunk_code = '\n'.join(lines[start:end])
                chunks.append((start + 1, end, chunk_code))
                start = end - overlap
            
            return chunks
        except Exception as e:
            logging.error(f"源码切片失败: {e}")
            return []


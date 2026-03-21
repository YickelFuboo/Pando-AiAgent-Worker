import logging
from typing import List,Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,delete
from app.domains.code_analysis.service.codechunk.models.model import RepoCodeChunks
from app.domains.code_analysis.service.codechunk.schemes.scheme import CodeChunkCreate,CodeChunkUpdate,SearchResponse,SearchResult,SearchRequest as SearchRequestDto
from app.domains.code_analysis.service.codechunk.constants import (
    get_chunk_source_vector_space,
    get_chunk_summary_vector_space,
    EMBEDDING_BATCH_SIZE
)
from app.domains.code_analysis.service.codesummary.services.code_summary import CodeSummary
from app.domains.code_analysis.service.codesummary.models.model import ContentType
from app.infrastructure.llms import embedding_factory
from app.infrastructure.llms.utils import truncate
from app.infrastructure.vector_store import VECTOR_STORE_CONN,SearchRequest,MatchDenseExpr
import numpy as np


class RepoCodeChunksMgmt:
    """管理代码片段数据表及对应内容的向量化"""
    
    def __init__(self, db_session: AsyncSession, repo_id: Optional[str] = None):
        self.db_session = db_session
        self.repo_id = repo_id
    
    async def create(self, data: CodeChunkCreate) -> RepoCodeChunks:
        """创建代码片段数据记录"""
        try:
            chunk_data = RepoCodeChunks(
                repo_id=data.repo_id,
                source_code=data.source_code,
                file_path=data.file_path,
                start_line=data.start_line,
                end_line=data.end_line,
                summary=None,
                is_summarized=False,
                is_source_vectorized=False,
                is_summary_vectorized=False
            )
            self.db_session.add(chunk_data)
            await self.db_session.commit()
            await self.db_session.refresh(chunk_data)
            return chunk_data
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"创建代码片段数据失败: {e}")
            raise
    
    async def get_by_id(self, id: str) -> Optional[RepoCodeChunks]:
        """根据ID获取代码片段数据"""
        try:
            result = await self.db_session.execute(
                select(RepoCodeChunks).where(RepoCodeChunks.id == id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logging.error(f"获取代码片段数据失败: {e}")
            return None
    
    async def get_by_repo_id(self, repo_id: str, limit: int = 100, offset: int = 0) -> List[RepoCodeChunks]:
        """根据代码仓ID获取代码片段数据列表"""
        try:
            result = await self.db_session.execute(
                select(RepoCodeChunks)
                .where(RepoCodeChunks.repo_id == repo_id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取代码片段数据列表失败: {e}")
            return []
    
    async def _get_source_unvectorized(self, limit: int = 100) -> List[RepoCodeChunks]:
        """获取未向量化源码的代码片段数据"""
        try:
            if not self.repo_id:
                logging.error("repo_id不能为空")
                return []
            query = select(RepoCodeChunks).where(
                RepoCodeChunks.is_source_vectorized == False,
                RepoCodeChunks.repo_id == self.repo_id
            )
            query = query.limit(limit)
            result = await self.db_session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取未向量化源码的代码片段数据失败: {e}")
            return []
    
    async def _get_summary_unvectorized(self, limit: int = 100) -> List[RepoCodeChunks]:
        """获取未向量化功能说明的代码片段数据"""
        try:
            if not self.repo_id:
                logging.error("repo_id不能为空")
                return []
            query = select(RepoCodeChunks).where(
                RepoCodeChunks.is_summary_vectorized == False,
                RepoCodeChunks.is_summarized == True,
                RepoCodeChunks.repo_id == self.repo_id
            )
            query = query.limit(limit)
            result = await self.db_session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取未向量化功能说明的代码片段数据失败: {e}")
            return []
    
    async def _get_unsummarized(self, limit: int = 100) -> List[RepoCodeChunks]:
        """获取未生成summary的代码片段数据"""
        try:
            if not self.repo_id:
                logging.error("repo_id不能为空")
                return []
            query = select(RepoCodeChunks).where(
                RepoCodeChunks.is_summarized == False,
                RepoCodeChunks.repo_id == self.repo_id
            )
            query = query.limit(limit)
            result = await self.db_session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取未生成summary的代码片段数据失败: {e}")
            return []
    
    async def update(self, id: str, data: CodeChunkUpdate) -> Optional[RepoCodeChunks]:
        """更新代码片段数据"""
        try:
            chunk_data = await self.get_by_id(id)
            if not chunk_data:
                return None
            
            if data.summary is not None:
                chunk_data.summary = data.summary
            if data.is_summarized is not None:
                chunk_data.is_summarized = data.is_summarized
            if data.is_source_vectorized is not None:
                chunk_data.is_source_vectorized = data.is_source_vectorized
            if data.is_summary_vectorized is not None:
                chunk_data.is_summary_vectorized = data.is_summary_vectorized
            
            await self.db_session.commit()
            await self.db_session.refresh(chunk_data)
            return chunk_data
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"更新代码片段数据失败: {e}")
            return None
    
    async def delete(self, id: str) -> bool:
        """删除代码片段数据"""
        try:
            chunk_data = await self.get_by_id(id)
            if not chunk_data:
                return False
            
            # 如果已向量化，先删除向量记录
            if chunk_data.is_source_vectorized or chunk_data.is_summary_vectorized:
                await self._delete_vector_record_by_id(chunk_data)
            
            await self.db_session.delete(chunk_data)
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除代码片段数据失败: {e}")
            return False

    async def delete_by_repo_id(self) -> bool:
        """根据代码仓ID删除代码片段数据
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 直接删除整个向量空间（更高效）
            await self._delete_vector_records_by_repo_id()
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoCodeChunks).where(RepoCodeChunks.repo_id == self.repo_id))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除代码片段数据失败: {e}")
            return False

    async def delete_by_repo_id_and_folder_path(self, folder_path: str) -> bool:
        """根据代码仓ID和文件夹路径删除代码片段数据
        
        使用文件夹路径前缀匹配文件路径，删除该文件夹下所有文件的代码片段
        
        Args:
            folder_path: 文件夹路径（用于前缀匹配）
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 先获取需要删除的记录，删除向量记录
            query = select(RepoCodeChunks).where(
                RepoCodeChunks.repo_id == self.repo_id,
                RepoCodeChunks.file_path.startswith(folder_path)
            )
            result = await self.db_session.execute(query)
            chunks_to_delete = list(result.scalars().all())
            for chunk in chunks_to_delete:
                if chunk.is_source_vectorized or chunk.is_summary_vectorized:
                    await self._delete_vector_record_by_id(chunk)
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoCodeChunks).where(
                RepoCodeChunks.repo_id == self.repo_id,
                RepoCodeChunks.file_path.startswith(folder_path)
            ))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除代码片段数据失败: {e}")
            return False

    async def delete_by_repo_id_and_file_path(self, file_path: str) -> bool:
        """根据代码仓ID和文件路径删除代码片段数据
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 批量删除向量记录（更高效）
            await self._delete_vector_records_by_repo_id_and_file_path(file_path)
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoCodeChunks).where(
                RepoCodeChunks.repo_id == self.repo_id,
                RepoCodeChunks.file_path == file_path
            ))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除代码片段数据失败: {e}")
            return False
    
    async def generate_summary(self, chunk_data: RepoCodeChunks) -> str:
        """生成代码片段功能描述"""
        try:
            summary = await CodeSummary.llm_summarize(
                chunk_data.source_code,
                ContentType.CODE_CHUNK
            )
            return summary
        except Exception as e:
            logging.error(f"生成代码片段摘要失败: {e}")
            return ""
    
    async def vectorize_source(self, chunks: List[RepoCodeChunks]) -> int:
        """向量化代码片段源码
        
        Args:
            chunks: RepoCodeChunks 列表（即使只有一条记录也使用列表格式）
            
        Returns:
            成功向量化的数量
        """
        if not chunks:
            return 0
        
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.error("无法创建嵌入模型")
                return 0
            
            # 获取模型最大token数
            max_tokens = embedding_model.configs.get("max_tokens", 8192)
            
            # 准备文本列表
            content_texts = [chunk.source_code for chunk in chunks]
            
            # 批量处理内容向量化
            content_vectors = np.array([])
            total_token_count = 0
            
            for batch_start in range(0, len(content_texts), EMBEDDING_BATCH_SIZE):
                batch_end = batch_start + EMBEDDING_BATCH_SIZE
                batch_content_texts = content_texts[batch_start:batch_end]
                
                # 截断文本到模型最大长度
                truncated_texts = [
                    truncate(text, max_tokens - 10) 
                    for text in batch_content_texts
                ]
                
                batch_vectors, token_count = await embedding_model.encode(truncated_texts)
                
                if batch_vectors is None or len(batch_vectors) == 0:
                    logging.error(f"批量向量化失败: batch_start={batch_start}, batch_end={batch_end}")
                    continue
                
                if len(content_vectors) == 0:
                    content_vectors = batch_vectors
                else:
                    content_vectors = np.concatenate((content_vectors, batch_vectors), axis=0)
                total_token_count += token_count
            
            if len(content_vectors) == 0:
                logging.error("向量化失败：没有生成任何向量")
                return 0
            
            # 确保向量数量与chunks数量一致
            if len(content_vectors) != len(chunks):
                logging.error(f"向量数量({len(content_vectors)})与chunks数量({len(chunks)})不匹配")
                return 0
            
            # 按repo_id分组处理
            repo_groups = {}
            for idx, chunk in enumerate(chunks):
                repo_id = chunk.repo_id
                if repo_id not in repo_groups:
                    repo_groups[repo_id] = []
                repo_groups[repo_id].append((chunk, content_vectors[idx]))
            
            success_count = 0
            for repo_id, chunk_vector_pairs in repo_groups.items():
                # 准备记录
                records = []
                vector_size = None
                for chunk, vector in chunk_vector_pairs:
                    vector_list = vector.tolist()
                    if vector_size is None:
                        vector_size = len(vector_list)
                    record = {
                        "id": chunk.id,
                        "repo_id": chunk.repo_id,
                        "source_code": chunk.source_code,
                        "file_path": chunk.file_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        f"q_{vector_size}_vec": vector_list
                    }
                    records.append(record)
                
                # 创建向量空间（使用第一个向量的维度）
                if records and vector_size:
                    space_name = await get_chunk_source_vector_space(repo_id, vector_size)
                    
                    # 批量插入记录
                    vector_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
                    if not vector_ids:
                        for chunk, _ in chunk_vector_pairs:
                            await self.update(chunk.id, CodeChunkUpdate(
                                is_source_vectorized=True
                            ))
                        success_count += len(chunk_vector_pairs)
                    else:
                        # 有失败（部分成功或全部失败），不更新数据库，下次继续处理
                        logging.warning(f"插入向量记录失败: 失败{len(vector_ids)}个，不更新数据库状态，下次继续处理")
            
            return success_count
        except Exception as e:
            logging.error(f"批量向量化代码片段源码失败: {e}")
            return 0
    
    async def vectorize_summary(self, chunks: List[RepoCodeChunks]) -> int:
        """向量化代码片段功能说明
        
        Args:
            chunks: RepoCodeChunks 列表（即使只有一条记录也使用列表格式）
            
        Returns:
            成功向量化的数量
        """
        if not chunks:
            return 0
        
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.error("无法创建嵌入模型")
                return 0
            
            # 获取模型最大token数
            max_tokens = embedding_model.configs.get("max_tokens", 8192)
            
            # 过滤掉没有summary的chunks
            chunks_with_summary = [chunk for chunk in chunks if chunk.summary]
            if not chunks_with_summary:
                return 0
            
            # 准备文本列表
            content_texts = [chunk.summary for chunk in chunks_with_summary]
            
            # 批量处理内容向量化
            content_vectors = np.array([])
            total_token_count = 0
            for batch_start in range(0, len(content_texts), EMBEDDING_BATCH_SIZE):
                batch_end = batch_start + EMBEDDING_BATCH_SIZE
                batch_content_texts = content_texts[batch_start:batch_end]
                
                # 截断文本到模型最大长度
                truncated_texts = [
                    truncate(text, max_tokens - 10) 
                    for text in batch_content_texts
                ]
                
                batch_vectors, token_count = await embedding_model.encode(truncated_texts)
                
                if batch_vectors is None or len(batch_vectors) == 0:
                    logging.error(f"批量向量化失败: batch_start={batch_start}, batch_end={batch_end}")
                    continue
                
                if len(content_vectors) == 0:
                    content_vectors = batch_vectors
                else:
                    content_vectors = np.concatenate((content_vectors, batch_vectors), axis=0)
                total_token_count += token_count
            
            if len(content_vectors) == 0:
                logging.error("向量化失败：没有生成任何向量")
                return 0
            
            # 确保向量数量与chunks数量一致
            if len(content_vectors) != len(chunks_with_summary):
                logging.error(f"向量数量({len(content_vectors)})与chunks数量({len(chunks_with_summary)})不匹配")
                return 0
            
            # 按repo_id分组处理
            repo_groups = {}
            for idx, chunk in enumerate(chunks_with_summary):
                repo_id = chunk.repo_id
                if repo_id not in repo_groups:
                    repo_groups[repo_id] = []
                repo_groups[repo_id].append((chunk, content_vectors[idx]))
            
            success_count = 0
            for repo_id, chunk_vector_pairs in repo_groups.items():
                # 准备记录
                records = []
                vector_size = None
                for chunk, vector in chunk_vector_pairs:
                    vector_list = vector.tolist()
                    if vector_size is None:
                        vector_size = len(vector_list)
                    record = {
                        "id": chunk.id,
                        "repo_id": chunk.repo_id,
                        "file_path": chunk.file_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "summary": chunk.summary,
                        f"q_{vector_size}_vec": vector_list
                    }
                    records.append(record)
                
                # 创建向量空间（使用第一个向量的维度）
                if records and vector_size:
                    space_name = await get_chunk_summary_vector_space(repo_id, vector_size)
                    
                    # 批量插入记录
                    vector_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
                    if not vector_ids:
                        # 空列表表示全部成功，批量更新数据库
                        for chunk, _ in chunk_vector_pairs:
                            await self.update(chunk.id, CodeChunkUpdate(
                                is_summary_vectorized=True
                            ))
                        success_count += len(chunk_vector_pairs)
                    else:
                        # 有失败（部分成功或全部失败），不更新数据库，下次继续处理
                        logging.warning(f"插入向量记录失败: 失败{len(vector_ids)}个，不更新数据库状态，下次继续处理")
            
            return success_count
        except Exception as e:
            logging.error(f"批量向量化代码片段功能说明失败: {e}")
            return 0
    
    async def scan_and_generate_summary(self, limit: int = 100) -> int:
        """批量生成代码片段功能描述"""
        try:
            unsummarized = await self._get_unsummarized(limit=limit)
            count = 0
            for chunk_data in unsummarized:
                try:
                    summary = await self.generate_summary(chunk_data)
                    if summary:
                        await self.update(chunk_data.id, CodeChunkUpdate(
                            summary=summary,
                            is_summarized=True
                        ))
                        count += 1
                except Exception as e:
                    logging.error(f"生成代码片段{chunk_data.id}摘要失败: {e}")
                    continue
            return count
        except Exception as e:
            logging.error(f"批量生成summary失败: {e}")
            return 0
    
    async def scan_and_vectorize_source(self, limit: int = 100) -> int:
        """批量向量化未向量化的代码片段源码"""
        try:
            unvectorized = await self._get_source_unvectorized(limit=limit)
            if not unvectorized:
                return 0
            return await self.vectorize_source(unvectorized)
        except Exception as e:
            logging.error(f"批量向量化源码失败: {e}")
            return 0
    
    async def scan_and_vectorize_summary(self, limit: int = 100) -> int:
        """批量向量化未向量化的代码片段功能说明"""
        try:
            unvectorized = await self._get_summary_unvectorized(limit=limit)
            if not unvectorized:
                return 0
            return await self.vectorize_summary(unvectorized)
        except Exception as e:
            logging.error(f"批量向量化功能说明失败: {e}")
            return 0
    
    async def search_by_source_vector(self, request: SearchRequestDto) -> SearchResponse:
        """向量搜索代码片段源码"""
        try:
            repo_id = request.repo_id or self.repo_id
            if not repo_id:
                logging.error("repo_id不能为空")
                return SearchResponse(results=[], total=0)
            
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.error("无法创建嵌入模型")
                return SearchResponse(results=[], total=0)
            
            query_vector, _ = await embedding_model.encode_queries(request.query)
            if query_vector is None:
                logging.error("查询向量化失败")
                return SearchResponse(results=[], total=0)
            
            # 获取向量维度
            vector_size = len(query_vector) if hasattr(query_vector, '__len__') else query_vector.shape[0]
            vector_field_name = f"q_{vector_size}_vec"
            
            vector_expr = MatchDenseExpr(
                vector_column_name=vector_field_name,
                embedding_data=query_vector.tolist(),
                embedding_data_type="float32",
                distance_type="cosine",
                topn=request.top_k
            )
            
            search_request = SearchRequest(
                match_exprs=[vector_expr],
                limit=request.top_k
            )
            
            space_name = await get_chunk_source_vector_space(repo_id, vector_size)
            space_names = [space_name]
            if request.file_path:
                search_request.condition = {"file_path": request.file_path}
            
            result = await VECTOR_STORE_CONN.search(space_names, search_request)
            
            total = VECTOR_STORE_CONN.get_total(result)
            fields = VECTOR_STORE_CONN.get_fields(result, ["id", "source_code", "file_path", "start_line", "end_line"])
            
            results = []
            for field_data in fields.values():
                chunk_id = field_data.get("id")
                if not chunk_id:
                    continue
                results.append(SearchResult(
                    id=chunk_id,
                    source_code=field_data.get("source_code", ""),
                    file_path=field_data.get("file_path", ""),
                    start_line=field_data.get("start_line", 0),
                    end_line=field_data.get("end_line", 0),
                    score=field_data.get("_score")
                ))
            
            return SearchResponse(results=results, total=total)
        except Exception as e:
            logging.error(f"搜索代码片段源码失败: {e}")
            return SearchResponse(results=[], total=0)
    
    async def search_by_summary_vector(self, request: SearchRequestDto) -> SearchResponse:
        """向量搜索代码片段功能说明"""
        try:
            repo_id = request.repo_id or self.repo_id
            if not repo_id:
                logging.error("repo_id不能为空")
                return SearchResponse(results=[], total=0)
            
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.error("无法创建嵌入模型")
                return SearchResponse(results=[], total=0)
            
            query_vector, _ = await embedding_model.encode_queries(request.query)
            if query_vector is None:
                logging.error("查询向量化失败")
                return SearchResponse(results=[], total=0)
            
            # 获取向量维度
            vector_size = len(query_vector) if hasattr(query_vector, '__len__') else query_vector.shape[0]
            vector_field_name = f"q_{vector_size}_vec"
            
            vector_expr = MatchDenseExpr(
                vector_column_name=vector_field_name,
                embedding_data=query_vector.tolist(),
                embedding_data_type="float32",
                distance_type="cosine",
                topn=request.top_k
            )
            
            search_request = SearchRequest(
                match_exprs=[vector_expr],
                limit=request.top_k
            )
            
            space_name = await get_chunk_summary_vector_space(repo_id, vector_size)
            space_names = [space_name]
            if request.file_path:
                search_request.condition = {"file_path": request.file_path}
            
            result = await VECTOR_STORE_CONN.search(space_names, search_request)
            
            total = VECTOR_STORE_CONN.get_total(result)
            fields = VECTOR_STORE_CONN.get_fields(result, ["id", "file_path", "start_line", "end_line", "summary"])
            
            # 从fields中获取chunk ID列表，用于批量查询数据库
            chunk_ids = [field_data.get("id") for field_data in fields.values() if field_data.get("id")]
            
            # 批量从数据库查询source_code
            chunk_map = {}
            if chunk_ids:
                query = select(RepoCodeChunks).where(RepoCodeChunks.id.in_(chunk_ids))
                db_result = await self.db_session.execute(query)
                chunks = list(db_result.scalars().all())
                chunk_map = {chunk.id: chunk for chunk in chunks}
            
            results = []
            for field_data in fields.values():
                chunk_id = field_data.get("id")
                if not chunk_id:
                    continue
                chunk_data = chunk_map.get(chunk_id)
                
                results.append(SearchResult(
                    id=chunk_id,
                    source_code=chunk_data.source_code if chunk_data else "",
                    file_path=field_data.get("file_path", ""),
                    start_line=field_data.get("start_line", 0),
                    end_line=field_data.get("end_line", 0),
                    summary=field_data.get("summary"),
                    score=field_data.get("_score")
                ))
            
            return SearchResponse(results=results, total=total)
        except Exception as e:
            logging.error(f"搜索代码片段功能说明失败: {e}")
            return SearchResponse(results=[], total=0)

    async def _delete_vector_record_by_id(self, chunk: RepoCodeChunks) -> None:
        """删除代码片段的向量记录（源码和功能说明）"""
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.warning(f"无法创建嵌入模型，跳过向量记录删除: chunk_id={chunk.id}")
                return
            
            # 删除源码向量记录
            if chunk.is_source_vectorized:
                try:
                    # 对source_code进行向量化以获取vector_size
                    batch_vectors, _ = await embedding_model.encode([chunk.source_code])
                    if batch_vectors is None or len(batch_vectors) == 0:
                        logging.warning(f"向量化失败，无法确定向量维度: chunk_id={chunk.id}")
                    else:
                        vector_size = len(batch_vectors[0].tolist())
                        space_name = await get_chunk_source_vector_space(chunk.repo_id, vector_size)
                        deleted_count = await VECTOR_STORE_CONN.delete_records(
                            space_name, 
                            {"id": chunk.id}
                        )
                        if deleted_count > 0:
                            logging.debug(f"删除源码向量记录成功: chunk_id={chunk.id}, space={space_name}, deleted={deleted_count}")
                except Exception as e:
                    # 空间可能不存在，记录警告但不影响删除流程
                    logging.warning(f"删除源码向量记录失败: chunk_id={chunk.id}, error={e}")
            
            # 删除功能说明向量记录
            if chunk.is_summary_vectorized and chunk.summary:
                try:
                    # 对summary进行向量化以获取vector_size
                    batch_vectors, _ = await embedding_model.encode([chunk.summary])
                    if batch_vectors is None or len(batch_vectors) == 0:
                        logging.warning(f"向量化失败，无法确定向量维度: chunk_id={chunk.id}")
                    else:
                        vector_size = len(batch_vectors[0].tolist())
                        space_name = await get_chunk_summary_vector_space(chunk.repo_id, vector_size)
                        deleted_count = await VECTOR_STORE_CONN.delete_records(
                            space_name, 
                            {"id": chunk.id}
                        )
                        if deleted_count > 0:
                            logging.debug(f"删除功能说明向量记录成功: chunk_id={chunk.id}, space={space_name}, deleted={deleted_count}")
                except Exception as e:
                    # 空间可能不存在，记录警告但不影响删除流程
                    logging.warning(f"删除功能说明向量记录失败: chunk_id={chunk.id}, error={e}")
        except Exception as e:
            logging.warning(f"删除向量记录失败: chunk_id={chunk.id}, error={e}")
    
    async def _delete_vector_records_by_repo_id(self) -> bool:
        """根据代码仓ID删除向量空间（源码和功能说明）
        
        直接删除整个向量空间，因为空间名称是基于repo_id的
        使用类变量 self.repo_id
        
        Returns:
            是否删除成功
        """
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.warning(f"无法创建嵌入模型，跳过向量空间删除: repo_id={self.repo_id}")
                return False
            
            # 使用一个示例文本来获取向量维度
            sample_text = "sample_text"
            batch_vectors, _ = await embedding_model.encode([sample_text])
            if batch_vectors is None or len(batch_vectors) == 0:
                logging.warning(f"向量化失败，无法确定向量维度: repo_id={self.repo_id}")
                return False
            
            vector_size = len(batch_vectors[0].tolist())
            success = True
            
            # 删除源码向量空间
            try:
                space_name = await get_chunk_source_vector_space(self.repo_id, vector_size)
                deleted = await VECTOR_STORE_CONN.delete_space(space_name)
                if deleted:
                    logging.debug(f"删除源码向量空间成功: repo_id={self.repo_id}, space={space_name}")
                else:
                    logging.warning(f"删除源码向量空间失败: repo_id={self.repo_id}, space={space_name}")
                    success = False
            except Exception as e:
                logging.warning(f"删除源码向量空间失败: repo_id={self.repo_id}, error={e}")
                success = False
            
            # 删除功能说明向量空间
            try:
                space_name = await get_chunk_summary_vector_space(self.repo_id, vector_size)
                deleted = await VECTOR_STORE_CONN.delete_space(space_name)
                if deleted:
                    logging.debug(f"删除功能说明向量空间成功: repo_id={self.repo_id}, space={space_name}")
                else:
                    logging.warning(f"删除功能说明向量空间失败: repo_id={self.repo_id}, space={space_name}")
                    success = False
            except Exception as e:
                logging.warning(f"删除功能说明向量空间失败: repo_id={self.repo_id}, error={e}")
                success = False
            
            return success
        except Exception as e:
            logging.warning(f"批量删除向量空间失败: repo_id={self.repo_id}, error={e}")
            return False
    
    async def _delete_vector_records_by_repo_id_and_file_path(self, file_path: str) -> int:
        """根据代码仓ID和文件路径批量删除向量记录（源码和功能说明）
        
        使用类变量 self.repo_id
        
        Args:
            file_path: 文件路径
            
        Returns:
            删除的记录总数
        """
        total_deleted = 0
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.warning(f"无法创建嵌入模型，跳过向量记录删除: repo_id={self.repo_id}, file_path={file_path}")
                return 0
            
            # 使用一个示例文本来获取向量维度
            sample_text = "sample_text"
            batch_vectors, _ = await embedding_model.encode([sample_text])
            if batch_vectors is None or len(batch_vectors) == 0:
                logging.warning(f"向量化失败，无法确定向量维度: repo_id={self.repo_id}, file_path={file_path}")
                return 0
            
            vector_size = len(batch_vectors[0].tolist())
            
            # 删除源码向量记录
            try:
                space_name = await get_chunk_source_vector_space(self.repo_id, vector_size)
                deleted_count = await VECTOR_STORE_CONN.delete_records(
                    space_name,
                    {
                        "repo_id": self.repo_id,
                        "file_path": file_path
                    }
                )
                total_deleted += deleted_count
                if deleted_count > 0:
                    logging.debug(f"删除源码向量记录成功: repo_id={self.repo_id}, file_path={file_path}, space={space_name}, deleted={deleted_count}")
            except Exception as e:
                logging.warning(f"删除源码向量记录失败: repo_id={self.repo_id}, file_path={file_path}, error={e}")
            
            # 删除功能说明向量记录
            try:
                space_name = await get_chunk_summary_vector_space(self.repo_id, vector_size)
                deleted_count = await VECTOR_STORE_CONN.delete_records(
                    space_name,
                    {
                        "repo_id": self.repo_id,
                        "file_path": file_path
                    }
                )
                total_deleted += deleted_count
                if deleted_count > 0:
                    logging.debug(f"删除功能说明向量记录成功: repo_id={self.repo_id}, file_path={file_path}, space={space_name}, deleted={deleted_count}")
            except Exception as e:
                logging.warning(f"删除功能说明向量记录失败: repo_id={self.repo_id}, file_path={file_path}, error={e}")
            
            return total_deleted
        except Exception as e:
            logging.warning(f"批量删除向量记录失败: repo_id={self.repo_id}, file_path={file_path}, error={e}")
            return total_deleted
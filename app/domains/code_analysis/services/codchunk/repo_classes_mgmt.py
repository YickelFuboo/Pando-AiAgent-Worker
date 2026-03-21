import logging
from typing import List,Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,delete,and_
from app.domains.code_analysis.service.codechunk.models.model import RepoClasses
from app.domains.code_analysis.service.codechunk.schemes.scheme import ClassDataCreate,ClassDataUpdate,SearchResponse,SearchResult,SearchRequest as SearchRequestDto
from app.domains.code_analysis.service.codechunk.constants import get_class_vector_space,EMBEDDING_BATCH_SIZE
from app.domains.code_analysis.service.codesummary.services.code_summary import CodeSummary
from app.domains.code_analysis.service.codesummary.models.model import ContentType
from app.infrastructure.llms import embedding_factory
from app.infrastructure.llms.utils import truncate
from app.infrastructure.vector_store import VECTOR_STORE_CONN,SearchRequest,MatchDenseExpr
import numpy as np


class RepoClassesMgmt:
    """管理类数据表及对应内容的向量化"""
    
    def __init__(self, db_session: AsyncSession, repo_id: Optional[str] = None):
        self.db_session = db_session
        self.repo_id = repo_id
    
    async def create(self, data: ClassDataCreate) -> RepoClasses:
        """创建类数据记录"""
        try:
            class_data = RepoClasses(
                repo_id=data.repo_id,
                source_code=data.source_code,
                file_path=data.file_path,
                start_line=data.start_line,
                end_line=data.end_line,
                class_name=data.class_name,
                class_type=data.class_type,
                summary=None,
                is_summarized=False,
                is_vectorized=False
            )
            self.db_session.add(class_data)
            await self.db_session.commit()
            await self.db_session.refresh(class_data)
            return class_data
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"创建类数据失败: {e}")
            raise
    
    async def get_by_id(self, class_id: str) -> Optional[RepoClasses]:
        """根据ID获取类数据"""
        try:
            result = await self.db_session.execute(
                select(RepoClasses).where(RepoClasses.id == class_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logging.error(f"获取类数据失败: {e}")
            return None
    
    async def get_by_repo_id(self, repo_id: str, limit: int = 100, offset: int = 0) -> List[RepoClasses]:
        """根据代码仓ID获取类数据列表"""
        try:
            result = await self.db_session.execute(
                select(RepoClasses)
                .where(RepoClasses.repo_id == repo_id)
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取类数据列表失败: {e}")
            return []
    
    async def _get_unvectorized(self, limit: int = 100) -> List[RepoClasses]:
        """获取未向量化的类数据（只返回有summary的）"""
        try:
            if not self.repo_id:
                logging.error("repo_id不能为空")
                return []
            query = select(RepoClasses).where(
                RepoClasses.is_vectorized == False,
                RepoClasses.is_summarized == True,
                RepoClasses.summary.isnot(None),
                RepoClasses.repo_id == self.repo_id
            )
            query = query.limit(limit)
            result = await self.db_session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取未向量化类数据失败: {e}")
            return []
    
    async def _get_unsummarized(self, limit: int = 100) -> List[RepoClasses]:
        """获取未生成summary的类数据"""
        try:
            if not self.repo_id:
                logging.error("repo_id不能为空")
                return []
            query = select(RepoClasses).where(
                RepoClasses.is_summarized == False,
                RepoClasses.repo_id == self.repo_id
            )
            query = query.limit(limit)
            result = await self.db_session.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logging.error(f"获取未生成summary的类数据失败: {e}")
            return []
    
    async def update(self, class_id: str, data: ClassDataUpdate) -> Optional[RepoClasses]:
        """更新类数据"""
        try:
            class_data = await self.get_by_id(class_id)
            if not class_data:
                return None
            
            if data.summary is not None:
                class_data.summary = data.summary
            if data.is_summarized is not None:
                class_data.is_summarized = data.is_summarized
            if data.is_vectorized is not None:
                class_data.is_vectorized = data.is_vectorized
            
            await self.db_session.commit()
            await self.db_session.refresh(class_data)
            return class_data
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"更新类数据失败: {e}")
            return None
    
    async def delete(self, class_id: str) -> bool:
        """删除类数据"""
        try:
            class_data = await self.get_by_id(class_id)
            if not class_data:
                return False
            
            # 如果已向量化，先删除向量记录
            if class_data.is_vectorized:
                await self._delete_vector_record_by_id(class_data)
            
            await self.db_session.delete(class_data)
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除类数据失败: {e}")
            return False
    
    async def delete_by_repo_id(self) -> bool:
        """根据代码仓ID删除类数据
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 直接删除整个向量空间（更高效）
            await self._delete_vector_records_by_repo_id()
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoClasses).where(RepoClasses.repo_id == self.repo_id))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除类数据失败: {e}")
            return False
    
    async def delete_by_repo_id_and_folder_path(self, folder_path: str) -> bool:
        """根据代码仓ID和文件夹路径删除类数据
        
        使用文件夹路径前缀匹配文件路径，删除该文件夹下所有文件的类数据
        
        Args:
            folder_path: 文件夹路径（用于前缀匹配）
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 先获取需要删除的记录，删除向量记录
            query = select(RepoClasses).where(
                RepoClasses.repo_id == self.repo_id,
                RepoClasses.file_path.startswith(folder_path)
            )
            result = await self.db_session.execute(query)
            classes_to_delete = list(result.scalars().all())
            for class_data in classes_to_delete:
                if class_data.is_vectorized:
                    await self._delete_vector_record_by_id(class_data)
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoClasses).where(
                RepoClasses.repo_id == self.repo_id,
                RepoClasses.file_path.startswith(folder_path)
            ))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除类数据失败: {e}")
            return False
    
    async def delete_by_repo_id_and_file_path(self, file_path: str) -> bool:
        """根据代码仓ID和文件路径删除类数据
        
        使用类变量 self.repo_id
        """
        if not self.repo_id:
            logging.error("repo_id不能为空")
            return False
        
        try:
            # 批量删除向量记录（更高效）
            await self._delete_vector_records_by_repo_id_and_file_path(file_path)
            
            # 删除数据库记录
            await self.db_session.execute(delete(RepoClasses).where(
                RepoClasses.repo_id == self.repo_id,
                RepoClasses.file_path == file_path
            ))
            await self.db_session.commit()
            return True
        except Exception as e:
            await self.db_session.rollback()
            logging.error(f"删除类数据失败: {e}")
            return False
    
    async def generate_summary(self, class_data: RepoClasses) -> str:
        """生成类功能描述"""
        try:
            content_type = ContentType.CLASS
            if class_data.class_type == "struct":
                content_type = ContentType.STRUCT
            elif class_data.class_type == "interface":
                content_type = ContentType.INTERFACE
            
            summary = await CodeSummary.llm_summarize(
                class_data.source_code,
                content_type
            )
            return summary
        except Exception as e:
            logging.error(f"生成类摘要失败: {e}")
            return ""
    
    async def vectorize(self, classes: List[RepoClasses]) -> int:
        """向量化类数据
        
        Args:
            classes: RepoClasses 列表（即使只有一条记录也使用列表格式）
            
        Returns:
            成功向量化的数量
        """
        if not classes:
            return 0
        
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.error("无法创建嵌入模型")
                return 0
            
            # 获取模型最大token数
            max_tokens = embedding_model.configs.get("max_tokens", 8192)
            
            # 过滤掉没有summary的classes，只对summary进行向量化
            classes_with_summary = [class_data for class_data in classes if class_data.summary]
            if not classes_with_summary:
                return 0
            
            # 准备文本列表（只使用summary）
            content_texts = [class_data.summary for class_data in classes_with_summary]
            
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
            
            # 确保向量数量与classes_with_summary数量一致
            if len(content_vectors) != len(classes_with_summary):
                logging.error(f"向量数量({len(content_vectors)})与classes数量({len(classes_with_summary)})不匹配")
                return 0
            
            # 按repo_id分组处理
            repo_groups = {}
            for idx, class_data in enumerate(classes_with_summary):
                repo_id = class_data.repo_id
                if repo_id not in repo_groups:
                    repo_groups[repo_id] = []
                repo_groups[repo_id].append((class_data, content_vectors[idx]))
            
            success_count = 0
            for repo_id, class_vector_pairs in repo_groups.items():
                # 准备记录
                records = []
                vector_size = None
                for class_data, vector in class_vector_pairs:
                    vector_list = vector.tolist()
                    if vector_size is None:
                        vector_size = len(vector_list)
                    record = {
                        "id": class_data.id,
                        "repo_id": class_data.repo_id,
                        "file_path": class_data.file_path,
                        "start_line": class_data.start_line,
                        "end_line": class_data.end_line,
                        "class_name": class_data.class_name,
                        "class_type": class_data.class_type,
                        "summary": class_data.summary,
                        f"q_{vector_size}_vec": vector_list
                    }
                    records.append(record)
                
                # 创建向量空间（使用第一个向量的维度）
                if records and vector_size:
                    space_name = await get_class_vector_space(repo_id, vector_size)
                    
                    # 批量插入记录
                    vector_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
                    if not vector_ids:
                        # 空列表表示全部成功，批量更新数据库
                        for class_data, _ in class_vector_pairs:
                            await self.update(class_data.id, ClassDataUpdate(
                                is_vectorized=True
                            ))
                        success_count += len(class_vector_pairs)
                    else:
                        # 有失败（部分成功或全部失败），不更新数据库，下次继续处理
                        logging.warning(f"插入向量记录失败: 失败{len(vector_ids)}个，不更新数据库状态，下次继续处理")
            
            return success_count
        except Exception as e:
            logging.error(f"批量向量化类数据失败: {e}")
            return 0
    
    async def scan_and_generate_summary(self, limit: int = 100) -> int:
        """批量生成类功能描述"""
        try:
            unsummarized = await self._get_unsummarized(limit=limit)
            count = 0
            for class_data in unsummarized:
                try:
                    summary = await self.generate_summary(class_data)
                    if summary:
                        await self.update(class_data.id, ClassDataUpdate(
                            summary=summary,
                            is_summarized=True
                        ))
                        count += 1
                except Exception as e:
                    logging.error(f"生成类{class_data.id}摘要失败: {e}")
                    continue
            return count
        except Exception as e:
            logging.error(f"批量生成summary失败: {e}")
            return 0
    
    async def scan_and_vectorize(self, limit: int = 100) -> int:
        """批量向量化未向量化的类数据"""
        try:
            unvectorized = await self._get_unvectorized(limit=limit)
            if not unvectorized:
                return 0
            return await self.vectorize(unvectorized)
        except Exception as e:
            logging.error(f"批量向量化失败: {e}")
            return 0

    async def search(self, request: SearchRequestDto) -> SearchResponse:
        """向量搜索类数据"""
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
            
            space_name = await get_class_vector_space(repo_id, vector_size)
            space_names = [space_name]
            if request.file_path:
                search_request.condition = {"file_path": request.file_path}
            
            result = await VECTOR_STORE_CONN.search(space_names, search_request)
            
            total = VECTOR_STORE_CONN.get_total(result)
            fields = VECTOR_STORE_CONN.get_fields(result, ["id", "file_path", "start_line", "end_line", "summary", "class_name"])
            
            # 从fields中获取class ID列表，用于批量查询数据库
            class_ids = [field_data.get("id") for field_data in fields.values() if field_data.get("id")]
            
            # 批量从数据库查询source_code
            class_map = {}
            if class_ids:
                query = select(RepoClasses).where(RepoClasses.id.in_(class_ids))
                db_result = await self.db_session.execute(query)
                classes = list(db_result.scalars().all())
                class_map = {cls.id: cls for cls in classes}
            
            results = []
            for field_data in fields.values():
                class_id = field_data.get("id")
                if not class_id:
                    continue
                class_data = class_map.get(class_id)
                
                results.append(SearchResult(
                    id=class_id,
                    source_code=class_data.source_code if class_data else "",
                    file_path=field_data.get("file_path", ""),
                    start_line=field_data.get("start_line", 0),
                    end_line=field_data.get("end_line", 0),
                    summary=field_data.get("summary"),
                    score=field_data.get("_score")
                ))
            
            return SearchResponse(results=results, total=total)
        except Exception as e:
            logging.error(f"搜索类数据失败: {e}")
            return SearchResponse(results=[], total=0)
    
    async def _delete_vector_record_by_id(self, class_data: RepoClasses) -> None:
        """删除类的向量记录"""
        try:
            embedding_model = embedding_factory.create_model()
            if not embedding_model:
                logging.warning(f"无法创建嵌入模型，跳过向量记录删除: class_id={class_data.id}")
                return
            
            if class_data.is_vectorized:
                try:
                    # 对summary进行向量化以获取vector_size
                    sample_text = "sample_text"
                    batch_vectors, _ = await embedding_model.encode([sample_text])
                    if batch_vectors is None or len(batch_vectors) == 0:
                        logging.warning(f"向量化失败，无法确定向量维度: class_id={class_data.id}")
                    else:
                        vector_size = len(batch_vectors[0].tolist())
                        space_name = await get_class_vector_space(class_data.repo_id, vector_size)
                        deleted_count = await VECTOR_STORE_CONN.delete_records(
                            space_name, 
                            {"id": class_data.id}
                        )
                        if deleted_count > 0:
                            logging.debug(f"删除类向量记录成功: class_id={class_data.id}, space={space_name}, deleted={deleted_count}")
                except Exception as e:
                    # 空间可能不存在，记录警告但不影响删除流程
                    logging.warning(f"删除类向量记录失败: class_id={class_data.id}, error={e}")
        except Exception as e:
            logging.warning(f"删除向量记录失败: class_id={class_data.id}, error={e}")
    
    async def _delete_vector_records_by_repo_id(self) -> bool:
        """根据代码仓ID删除向量空间
        
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
            
            # 删除类向量空间
            try:
                space_name = await get_class_vector_space(self.repo_id, vector_size)
                deleted = await VECTOR_STORE_CONN.delete_space(space_name)
                if deleted:
                    logging.debug(f"删除类向量空间成功: repo_id={self.repo_id}, space={space_name}")
                else:
                    logging.warning(f"删除类向量空间失败: repo_id={self.repo_id}, space={space_name}")
                    return False
            except Exception as e:
                logging.warning(f"删除类向量空间失败: repo_id={self.repo_id}, error={e}")
                return False
            
            return True
        except Exception as e:
            logging.warning(f"批量删除向量空间失败: repo_id={self.repo_id}, error={e}")
            return False
    
    async def _delete_vector_records_by_repo_id_and_file_path(self, file_path: str) -> int:
        """根据代码仓ID和文件路径批量删除向量记录
        
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
            
            # 删除类向量记录
            try:
                space_name = await get_class_vector_space(self.repo_id, vector_size)
                deleted_count = await VECTOR_STORE_CONN.delete_records(
                    space_name,
                    {
                        "repo_id": self.repo_id,
                        "file_path": file_path
                    }
                )
                total_deleted += deleted_count
                if deleted_count > 0:
                    logging.debug(f"删除类向量记录成功: repo_id={self.repo_id}, file_path={file_path}, space={space_name}, deleted={deleted_count}")
            except Exception as e:
                logging.warning(f"删除类向量记录失败: repo_id={self.repo_id}, file_path={file_path}, error={e}")
            
            return total_deleted
        except Exception as e:
            logging.warning(f"批量删除向量记录失败: repo_id={self.repo_id}, file_path={file_path}, error={e}")
            return total_deleted

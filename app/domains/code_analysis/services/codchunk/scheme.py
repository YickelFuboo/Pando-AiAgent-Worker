from typing import List,Optional

from pydantic import BaseModel


class CodeChunkCreate(BaseModel):
    """创建代码片段请求"""
    repo_id: str
    source_code: str
    file_path: str
    start_line: int
    end_line: int


class CodeChunkUpdate(BaseModel):
    """更新代码片段请求"""
    summary: Optional[str] = None
    is_summarized: Optional[bool] = None
    is_source_vectorized: Optional[bool] = None
    is_summary_vectorized: Optional[bool] = None


class FunctionDataCreate(BaseModel):
    """创建函数数据请求"""
    repo_id: str
    source_code: str
    file_path: str
    start_line: int
    end_line: int
    function_name: Optional[str] = None
    function_signature: Optional[str] = None
    summary: Optional[str] = None


class FunctionDataUpdate(BaseModel):
    """更新函数数据请求"""
    summary: Optional[str] = None
    is_summarized: Optional[bool] = None
    is_vectorized: Optional[bool] = None


class ClassDataCreate(BaseModel):
    """创建类数据请求"""
    repo_id: str
    source_code: str
    file_path: str
    start_line: int
    end_line: int
    class_name: Optional[str] = None
    class_type: Optional[str] = None
    summary: Optional[str] = None


class ClassDataUpdate(BaseModel):
    """更新类数据请求"""
    summary: Optional[str] = None
    is_summarized: Optional[bool] = None
    is_vectorized: Optional[bool] = None


class SearchRequest(BaseModel):
    """搜索请求"""
    repo_id: str
    query: str
    top_k: int = 10
    file_path: Optional[str] = None


class SearchResult(BaseModel):
    """搜索结果"""
    id: str
    source_code: Optional[str] = None
    file_path: str
    start_line: int
    end_line: int
    summary: Optional[str] = None
    score: Optional[float] = None


class SearchResponse(BaseModel):
    """搜索响应"""
    results: List[SearchResult]
    total: int


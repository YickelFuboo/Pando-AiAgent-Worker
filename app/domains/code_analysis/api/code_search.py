from typing import Dict
from fastapi import APIRouter, HTTPException, status
from app.domains.code_analysis.schemes.code_search import RelatedFilesSearchRequest, SimilarCodeSearchRequest
from app.domains.code_analysis.services.code_search_service import CodeSearchService


router = APIRouter(prefix="/code-search", tags=["代码检索"])


@router.post("/{repo_id}/similar-code")
async def search_similar_code(
    repo_id: str,
    payload: SimilarCodeSearchRequest,
) -> Dict[str, object]:
    """输入代码文本，在行块向量索引中做相似检索。"""
    try:
        return await CodeSearchService.search_similar_code(
            repo_id=repo_id,
            code_text=payload.code_text,
            top_k=payload.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{repo_id}/related-files")
async def search_related_files(
    repo_id: str,
    payload: RelatedFilesSearchRequest,
) -> Dict[str, object]:
    """用关键词在符号摘要向量与行块向量中检索，合并结果并按文件路径与行号去重。"""
    try:
        return await CodeSearchService.search_related_files(
            repo_id=repo_id,
            keywords=payload.keywords,
            top_k=payload.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

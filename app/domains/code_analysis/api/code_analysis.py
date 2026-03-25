from typing import Dict
from fastapi import APIRouter, Body, HTTPException, status
from app.domains.code_analysis.services.repo_analysis_service import RepoAnalysisService


router = APIRouter(prefix="/repo-analysis", tags=["代码仓分析"])


@router.post("/{repo_id}/start-analysis")
async def start_repo_analysis(
    repo_id: str,
    target_rel_path: str | None = Body(default=None, embed=True),
) -> Dict[str, object]:
    """启动仓库源码分析。"""
    try:
        return await RepoAnalysisService.start_scan(
            repo_id=repo_id,
            target_rel_path=target_rel_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{repo_id}/summary")
async def get_repo_analysis_summary(repo_id: str) -> Dict[str, object]:
    """仓库扫描状态 + 各文件分析状态汇总。"""
    return await RepoAnalysisService.get_summary(repo_id)


@router.get("/{repo_id}/scan-status")
async def get_repo_scan_status(repo_id: str) -> Dict[str, object]:
    """仅扫描任务（仓级）状态，便于轮询。"""
    return await RepoAnalysisService.get_scan_status(repo_id)

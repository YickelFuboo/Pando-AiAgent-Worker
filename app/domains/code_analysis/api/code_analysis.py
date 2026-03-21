from typing import Any,Dict
from fastapi import APIRouter,Depends,HTTPException,status,Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database import get_db
from app.domains.code_analysis.service.code_analysis import CodeAnalysisService


router=APIRouter(prefix="/code-analysis",tags=["代码预分析与向量检索"])


@router.post("/run", response_model=Dict[str,Any])
async def run_code_analysis_endpoint(
    repo_mgmt_id:str=Body(..., embed=True),
    db:AsyncSession=Depends(get_db)
):
    """运行代码分析"""
    try:
        stats=await CodeAnalysisService(repo_mgmt_id, db).run()
        return stats
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"预分析失败:{e}")


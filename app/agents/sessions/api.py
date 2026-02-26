from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Body
from .manager import session_manager
from .schemes import SessionCreate, SessionInfo, SessionDetail


# 主路由
router = APIRouter(prefix="/sessions", tags=["会话管理"])


@router.post(
    "/create",
    summary="创建会话",
    description="创建一个新的会话",
    response_model=SessionInfo,
)
async def create_session(session_create: SessionCreate):
    """创建会话（DB 由 Store 内部管理，不由 API 注入）"""
    session_id = await session_manager.create_session(**session_create.model_dump())
    session = await session_manager.get_session(session_id)
    return SessionInfo(**session.to_info_summary())


@router.get(
    "/list",
    summary="获取所有会话",
    description="获取所有会话的列表",
    response_model=List[SessionInfo],
)
async def list_sessions(
    session_type: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """获取会话列表；可选按 session_type 或 user_id 过滤。"""
    if session_type:
        sessions = await session_manager.get_sessions_by_type(session_type)
    elif user_id:
        sessions = await session_manager.get_sessions_by_user_id(user_id)
    else:
        sessions = await session_manager.get_all_sessions()
    return [SessionInfo(**s.to_info_summary()) for s in sessions]


@router.get(
    "/info/{session_id}",
    summary="获取会话信息",
    description="获取指定会话的详细信息",
    response_model=SessionDetail,
)
async def get_session_info(session_id: str):
    """获取会话信息"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetail(**session.to_info_detail())


@router.put(
    "/metadata/{session_id}",
    summary="更新会话元数据",
    description="更新指定会话的元数据",
    responses={200: {"description": "Successfully updated"}, 404: {"description": "Session not found"}},
)
async def update_metadata(
    session_id: str,
    metadata: Dict[str, Any] = Body(
        example={"title": "会话标题", "source": "web"},
        description="会话元数据，任意键值对",
    ),
):
    """更新会话元数据"""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    for key, value in metadata.items():
        session.set_metadata(key, value)
    await session_manager.save_session(session_id)
    return {"status": "success"}


@router.delete(
    "/{session_id}",
    summary="删除会话",
    description="删除指定的会话",
)
async def delete_session(session_id: str):
    """删除会话"""
    if not await session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted successfully"}


@router.delete(
    "/history/{session_id}",
    summary="清空会话历史",
    description="清空指定的会话历史",
)
async def clear_history(session_id: str):
    """清空会话历史"""
    if not await session_manager.clear_history(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "History cleared successfully"}

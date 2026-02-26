from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from fastapi import Body
from app.agents.model import AgentType
from .manager import session_manager
from .models import Message
from .schemes import SessionCreate, SessionInfo, SessionDetail

router = APIRouter()

@router.post("/create", 
    summary="创建会话",
    description="创建一个新的会话",
    response_model=SessionInfo)
async def create_session(session_create: SessionCreate):
    """创建会话"""
    session_id = session_manager.create_session(**session_create.model_dump())
    session = session_manager.get_session(session_id)
    return session.to_info_summary()
@router.get("/list", 
    summary="获取所有会话",
    description="获取所有会话的列表",
    response_model=List[SessionInfo])
async def list_sessions(
    agent_type: Optional[AgentType] = None,
    username: Optional[str] = None
):
    """获取会话列表
    
    Args:
        agent_type: 可选,按代理类型过滤
        username: 可选,按用户名过滤
    """
    if agent_type:
        sessions = session_manager.get_sessions_by_type(agent_type)
    elif username:
        sessions = session_manager.get_sessions_by_user(username)
    else:
        sessions = session_manager.get_all_sessions()
        
    return [SessionInfo(**session.to_info_summary()) for session in sessions]

@router.get("/info/{session_id}", 
    summary="获取会话信息",
    description="获取指定会话的详细信息",
    response_model=SessionDetail)
async def get_session_info(session_id: str):
    """获取会话信息"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_info_detail()

# 设置当前会话配置，入参是key-value列表，结果直接返回200响应
@router.put("/metadata/{session_id}", 
    summary="更新会话信息",
    description="更新指定会话的元数据",
    response_model=None,
    responses={
        200: {"description": "Successfully updated"},
        404: {"description": "Session not found"}
    }) 
async def update_metadata(
    session_id: str, 
    metadata: Dict[str, Any] = Body(
        example={
            "project_info": {
                "project_dir": "E:\\MyProject\\test",
                "owner": "anyone",
                "project_name": "test",
                "project_description": "a test project"
            }
        },
        description="会话配置信息，包含project_info对象"
    )
):
    """更新会话信息
    
    示例请求体:
    ```json
    {
        "project_info": {
            "project_dir": "E:\\MyProject\\test",
            "owner": "anyone",
            "project_name": "test",
            "project_description": "a test project"
        }
    }
    ```
    """
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404, 
            detail="Session not found"
        )   
    for key, value in metadata.items():
        session.set_metadata(key, value)
    session_manager.save_session(session)
    return {"status": "success"}  # 直接返回成功状态

@router.delete("/{session_id}",
    summary="删除会话",
    description="删除指定的会话")
async def delete_session(session_id: str):
    """删除会话"""
    if not session_manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted successfully"}

@router.delete("/history/{session_id}",
    summary="清空会话历史",
    description="清空指定的会话历史")
async def clear_history(session_id: str):
    """清空会话历史"""
    if not session_manager.clear_history(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "History cleared successfully"}

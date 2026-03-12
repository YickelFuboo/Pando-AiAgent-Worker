from fastapi import APIRouter, HTTPException
import logging
from app.channel.schemes import UserRequest, UserResponse
from app.agents.core.react import ReActAgent
from app.agents.sessions.manager import SESSION_MANAGER


router = APIRouter()


@router.post("/chat", response_model=UserResponse)
async def chat(request: UserRequest):
    """聊天接口"""
    try:
        if request.session_id is None:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = await SESSION_MANAGER.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=400, detail="Session not found")

        agent = ReActAgent(
            agent_type="chat_agent",
            channel_type="Restful",
            channel_id=request.session_id,
            session_id=request.session_id, 
            workspace_index=request.session_id,
            user_id=request.user_id,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model,
        )

        # 运行Agent
        result = await agent.run(request.user_question)

        return UserResponse(session_id=request.session_id, content=result)
    except Exception as e:
        logging.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

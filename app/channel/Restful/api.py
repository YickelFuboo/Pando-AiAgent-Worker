import logging
from fastapi import APIRouter, HTTPException
from app.channel.schemes import UserRequest, UserResponse
from app.agents.sessions.message import Message
from app.agents.sessions.manager import SESSION_MANAGER
from app.infrastructure.llms.chat_models.factory import llm_factory


router = APIRouter()


SYSTEM_PROMPT = "You are a helpful assistant Pando, please give a detailed answer to the user's question."
USER_PROMPT = ""

@router.post("/chat", response_model=UserResponse)
async def chat(request: UserRequest):
    """聊天接口"""
    try:
        if request.session_id is None:
            raise HTTPException(status_code=400, detail="session_id is required")

        session = await SESSION_MANAGER.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=400, detail="Session not found")
        await SESSION_MANAGER.update_session(
            request.session_id,
            channel_type="Restful",
            metadata={"channel_id": request.session_id},
        )

        llm = llm_factory.create_model(provider=request.llm_provider, model=request.llm_model)
        history = await SESSION_MANAGER.get_context(request.session_id, max_messages=20)
        response, token_count = await llm.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
            user_question=request.content,
            history=history,
            temperature=0.7,
        )
        if not response.success:
            raise Exception(response.content)
        # 记录历史消息
        await SESSION_MANAGER.add_message(request.session_id, Message.user_message(request.content))
        await SESSION_MANAGER.add_message(request.session_id, Message.assistant_message(response.content))
        return UserResponse(session_id=request.session_id, content=response.content)
    except Exception as e:
        logging.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

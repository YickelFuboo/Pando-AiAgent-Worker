import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, HTTPException
from starlette.websockets import WebSocketDisconnect
from app.agents.bus.queues import CHANNEL_OUTBOUND_CALLBACKS, MESSAGE_BUS, InboundMessage, OutboundMessage
from .manager import WEBSOCKET_MANAGER
from .scheme import WebSocketMessage, WebSocketMessageType


router = APIRouter()


# 采用websocket模式连接前后端
@router.websocket("/{agent_type}/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    """WebSocket 连接端点""" 
    try:
        # 判断session是否存在
        session_id = websocket.path_params.get("session_id")
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")

        # 处理请求处理
        agent_type = websocket.path_params.get("agent_type")
        if not agent_type:
            raise HTTPException(status_code=400, detail="Agent type is required")

        # 建立websocket连接
        await WEBSOCKET_MANAGER.connect(client_id=session_id, websocket=websocket)

        # 发送连接成功消息
        await WEBSOCKET_MANAGER.send_message(
            client_id=session_id,
            message=WebSocketMessage(
                message_type=WebSocketMessageType.CONNECT_SUCCESS,
                current_session_id=session_id,
                content="Session Connected"
            )
        )
            
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    parsed = json.loads(data)
                    content = parsed.get("content", data)
                    llm_provider = parsed.get("llm_provider", "")
                    llm_model = parsed.get("llm_model", "")
                except json.JSONDecodeError:
                    content = data
                    llm_provider = ""
                    llm_model = ""
                inbound_msg = InboundMessage(
                    channel_type="websocket",
                    channel_id=session_id,
                    user_id=session_id,
                    session_id=session_id,
                    agent_type=agent_type,
                    content=content,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
                await MESSAGE_BUS.push_inbound(inbound_msg)
        except WebSocketDisconnect:
            logging.info(f"WebSocket client disconnected: {session_id}")
        except asyncio.TimeoutError:
            logging.error(f"Agent process timeout for session {session_id}")
            await WEBSOCKET_MANAGER.send_message(
                client_id=session_id,
                message=WebSocketMessage(
                    message_type=WebSocketMessageType.ERROR,
                    current_session_id=session_id,
                    content="Process timeout after 5 minutes")
            )
        except Exception as e:
            logging.error(f"Error in agent process: {str(e)}")
            await WEBSOCKET_MANAGER.send_message(
                client_id=session_id,
                message=WebSocketMessage(
                    message_type=WebSocketMessageType.ERROR,
                    current_session_id=session_id,
                    content=f"Error: {str(e)}")
            )
            
    except Exception as e:
        logging.error(f"WebSocket connection error: {str(e)}")
    finally:
        # 确保连接被正确关闭
        if session_id in WEBSOCKET_MANAGER.active_connections:
            WEBSOCKET_MANAGER.disconnect(session_id)
            logging.info(f"WebSocket disconnected: {session_id}")

def _on_websocket_outbound(msg: OutboundMessage) -> None:
    """向对端发送消息的回调，供 MESSAGE_BUS 使用"""

    async def _send():
        try:
            await WEBSOCKET_MANAGER.send_message(
                client_id=msg.session_id,
                message=WebSocketMessage(
                    message_type=WebSocketMessageType.RESPONSE,
                    current_session_id=msg.session_id,
                    content=msg.content,
                ),
            )
        except Exception as e:
            logging.error(f"WebSocket send outbound failed: {e}")

    asyncio.create_task(_send())

CHANNEL_OUTBOUND_CALLBACKS["websocket"] = _on_websocket_outbound

from fastapi import WebSocket
from typing import Dict, Any
import asyncio
from app.logger import logger
from .scheme import WebSocketMessage

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, client_id: str, websocket: WebSocket):
        """建立新的WebSocket连接"""
        logger.info(f"WebSocket connecting: {client_id}")
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket connected: {client_id}")
        
    async def disconnect(self, client_id: str):
        """关闭WebSocket连接"""
        logger.info(f"WebSocket disconnecting: {client_id}")
        try:
            if client_id in self.active_connections:
                await self.active_connections[client_id].close()
                del self.active_connections[client_id]
                logger.info(f"WebSocket disconnected: {client_id}")    
        except Exception as e:
            logger.info(f"Error closing connection: {str(e)}")
            
    def get_handler(self, client_id: str) -> WebSocket:
        """获取WebSocket处理器"""
        return self.active_connections.get(client_id)
    
    async def is_connected(self, client_id: str) -> bool:
        """检查WebSocket连接是否还活着
        
        通过尝试发送ping消息来检查连接状态
        """
        if client_id not in self.active_connections:
            return False
            
        try:
            websocket = self.active_connections[client_id]
            await websocket.send_text("ping")
            await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            return True
        except Exception as e:
            logger.info(f"Connection check failed for {client_id}: {str(e)}")
            self.disconnect(client_id)
            return False   
         
    async def send_message(self, client_id: str, message: WebSocketMessage):
        """发送消息到客户端"""
        logger.info(f"Sending {message.message_type} to {client_id}")
        
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message.to_dict())
                logger.info(f"Message sent successfully")
            except Exception as e:
                logger.info(f"Error sending message: {str(e)}")
                self.disconnect(client_id)
        else:
            raise Exception(f"No active connection for {client_id}")

    async def get_websocket(self, client_id: str) -> WebSocket:
        """获取WebSocket"""
        if client_id not in self.active_connections:
            raise Exception(f"No active connection for {client_id}")
        
        return self.active_connections.get(client_id)

WEBSOCKET_MANAGER = WebSocketManager()
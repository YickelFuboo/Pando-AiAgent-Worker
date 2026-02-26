from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import os
import uuid
from app.agents.model import AgentType
from app.logger import logger
from .models import Message
from .session import Session

class SessionManager:
    """会话管理器
    
    统一使用基础 Session 类,通过 metadata 存储不同类型会话的特定信息
    """
    def __init__(
        self, 
        storage_dir: str = "data/sessions"
    ):
        self.storage_dir = storage_dir
        self.sessions: Dict[str, Session] = {}
        self._load_sessions()

    def _load_sessions(self):
        """从存储加载会话"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            logger.info(f"Created sessions directory: {self.storage_dir}")
            return

        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.json'):
                session_id = filename[:-5]
                session_path = os.path.join(self.storage_dir, filename)
                try:
                    with open(session_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # 使用完整数据创建 Session
                        session = Session(**data)
                        self.sessions[session_id] = session
                        logger.info(f"Loaded session: {session_id}")
                except Exception as e:
                    logger.error(f"Error loading session {session_id}: {e}")

    def create_session(
        self,
        agent_type: AgentType,
        username: str = "anonymous",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        llm_name: Optional[str] = None,
        is_master_session: bool = True,
        parent_session_id: Optional[str] = None
    ) -> str:
        """创建新会话"""
        # 生成包含时间戳的会话ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]  # 取UUID的前8位作为随机后缀
        session_id = f"session_{timestamp}_{random_suffix}"
        
        session = Session(
            session_id=session_id,
            username=username,
            description=description,
            agent_type=agent_type,
            llm_name=llm_name or "default",
            is_master_session=is_master_session,
            parent_session_id=parent_session_id
        )
        
        # 设置元数据
        if metadata:
            for key, value in metadata.items():
                session.set_metadata(key, value)
        
        # 如果指定了父会话，建立关联关系
        if parent_session_id and parent_session_id in self.sessions:
            parent_session = self.sessions[parent_session_id]
            parent_session.add_sub_session(session_id)
            self.save_session(parent_session)
            logger.info(f"Created sub-session {session_id} under parent {parent_session_id}")
        else:
            logger.info(f"Created new session: {session_id}")
        
        self.sessions[session_id] = session
        self.save_session(session)
        return session_id

    async def add_message(
        self,
        session_id: str,
        message: Message
    ) -> bool:
        """添加消息到会话"""
        session = self.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False
            
        try:
            # 添加消息并自动处理压缩
            await session.add_message(message)
            
            # 保存会话
            self.save_session(session)
            #logger.info(f"Added message to session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding message to session {session_id}: {e}")
            return False

    def save_session(self, session: Session):
        """保存会话
        
        保存完整的会话数据到文件系统
        """
        session_path = os.path.join(self.storage_dir, f"{session.session_id}.json")
        try:
            # 使用 model_dump() 保存所有数据
            session_data = session.model_dump()
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            #logger.info(f"Saved session: {session.session_id}")
        except Exception as e:
            logger.error(f"Error saving session {session.session_id}: {e}")

    def get_all_sessions(self) -> List[Session]:
        """获取所有会话"""
        sessions = [
            session for session in self.sessions.values()
            if session.is_master_session
        ]
        logger.info(f"Found {len(sessions)} master sessions")
        return sessions

    def get_sessions_by_type(self, agent_type: AgentType) -> List[Session]:
        """获取指定类型的所有会话"""
        sessions = [
            session for session in self.sessions.values()
            if session.agent_type == agent_type and session.is_master_session
        ]
        logger.info(f"Found {len(sessions)} sessions of type {agent_type}")
        return sessions

    def get_sessions_by_user(self, username: str) -> List[Session]:
        """获取指定用户的所有会话"""
        sessions = [
            session for session in self.sessions.values()
            if session.username == username and session.is_master_session
        ]
        logger.info(f"Found {len(sessions)} sessions for user {username}")
        return sessions
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        if session_id not in self.sessions:
            logger.warning(f"Session not found: {session_id}")
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id not in self.sessions:
            logger.warning(f"Cannot delete: session not found: {session_id}")
            return False
        
        session = self.sessions[session_id]
        
        # 处理父子会话关系
        parent_id = session.get_parent_session()
        if parent_id and parent_id in self.sessions:
            parent_session = self.sessions[parent_id]
            parent_session.remove_sub_session(session_id)
            self.save_session(parent_session)
            
        # 递归删除所有子会话
        for sub_session_id in session.get_sub_sessions():
            self.delete_session(sub_session_id)
        
        session_path = os.path.join(self.storage_dir, f"{session_id}.json")
        try:
            os.remove(session_path)
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False

    def clear_history(self, session_id: str) -> bool:
        """清空会话历史"""
        session = self.get_session(session_id)
        if not session:
            logger.warning(f"Cannot clear history: session not found: {session_id}")
            return False
        
        try:
            session.original_messages.clear()
            session.compressed_messages.clear()
            session.last_updated = datetime.now()
            self.save_session(session)
            logger.info(f"Cleared history for session: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing history for session {session_id}: {e}")
            return False

# 创建全局会话管理器实例
session_manager = SessionManager() 
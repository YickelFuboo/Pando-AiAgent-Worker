"""会话管理器：按配置选用存储，提供创建、查询、更新、删除等接口。"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from .message import Message
from .session import Session
from .store import SessionStore, LocalFileSessionStore, DatabaseSessionStore
from .compaction import SessionCompaction
from app.config.settings import settings


class SessionManager:
    """会话管理器：按需加载 + 内存缓存，支持本地文件或数据库存储。"""

    def __init__(self) -> None:
        self._store: SessionStore = (
            LocalFileSessionStore() if settings.agent_session_use_local_storage
            else DatabaseSessionStore()
        )
        self.sessions: Dict[str, Session] = {}

    async def create_session(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        channel_type: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None
    ) -> str:
        """创建新会话。DB 由 Store 内部管理，不由 API 注入。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        session_id = f"session_{timestamp}_{random_suffix}"
        session = Session(
            session_id=session_id,
            user_id=user_id or "anonymous",
            description=description or "",
            agent_type=agent_type or "default",
            channel_type=channel_type or "",
            llm_provider=llm_provider or "",
            llm_model=llm_model or "",
            metadata=metadata or {},
        )
        self.sessions[session_id] = session
        await self._store.save(session)

        logging.info("Created session: %s", session_id)
        return session_id

    async def update_session(self, session_id: str, description: Optional[str] = None, agent_type: Optional[str] = None, channel_type: Optional[str] = None, llm_provider: Optional[str] = None, llm_model: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新会话"""
        session = await self.get_session(session_id)
        if not session:
            return False        
        session.description = description or session.description
        session.agent_type = agent_type or session.agent_type
        session.channel_type = channel_type or session.channel_type
        session.llm_provider = llm_provider or session.llm_provider
        session.llm_model = llm_model or session.llm_model
        if metadata:
            for key, value in metadata.items():
                session.metadata.update({key: value})
        session.last_updated = datetime.now()
        await self._store.save(session)
        return True

    async def add_message(self, session_id: str, message: Message) -> bool:
        """添加消息到会话"""
        session = await self.get_session(session_id)
        if not session:
            return False
        try:
            session.messages.append(message)
            session.last_updated = datetime.now()
            await self._store.save(session)
            return True
        except Exception as e:
            logging.error("Error adding message to session %s: %s", session_id, e)
            return False
    
    async def get_messages(self, session_id: str) -> List[Message]:
        """Get messages from session"""
        session = await self.get_session(session_id)
        if not session:
            return []
        return session.messages or []

    async def get_context(self, session_id: str, max_messages: int = 500) -> List[Dict[str, Any]]:
        """获取会话上下文（未合并消息），供 LLM 使用。"""
        session = await self.get_session(session_id)
        if not session:
            return []
        return session.to_context(max_messages=max_messages)

    async def get_all_sessions(
        self,
        *,
        agent_type: Optional[str] = None,
        channel_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Session]:
        """获取会话列表；过滤条件传给 store，DB 层 WHERE 查询避免全量加载。"""
        all_sessions = await self._store.get_all(
            agent_type=agent_type,
            channel_type=channel_type,
            user_id=user_id,
        )
        self.sessions.update({s.session_id: s for s in all_sessions})
        return all_sessions

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话。未命中缓存时从 store 按需加载并写入缓存。"""
        if session_id in self.sessions:
            return self.sessions[session_id]

        session = await self._store.get(session_id)
        if session:
            self.sessions[session_id] = session
            return session

        logging.warning("Session not found: %s", session_id)
        return None

    async def delete_session(self, session_id: str) -> bool:
        """删除会话。先删 store，再清理缓存。"""
        ok = await self._store.delete(session_id)
        if ok:
            if session_id in self.sessions:
                del self.sessions[session_id]
            logging.info("Deleted session: %s", session_id)
        else:
            logging.warning("Cannot delete: session not found: %s", session_id)
        return ok

    async def save_session(self, session_id: str) -> None:
        """持久化会话(如更新元数据后调用)。"""
        session = await self.get_session(session_id)
        if session:
            await self._store.save(session)

    async def clear_history(self, session_id: str) -> bool:
        """清空会话历史"""
        session = await self.get_session(session_id)
        if not session:
            logging.warning("Cannot clear history: session not found: %s", session_id)
            return False
        try:
            session.clear()
            await self._store.save(session)
            logging.info("Cleared history for session: %s", session_id)
            return True
        except Exception as e:
            logging.error("Error clearing history for session %s: %s", session_id, e)
            return False

    async def compact_session(
        self,
        session_id: str,
        keep_last_n: int = 0,
    ) -> bool:
        """对会话执行压缩：生成摘要并记录到 Session.compactions，不删除历史消息。

        Args:
            session_id: 会话 ID
            keep_last_n: 保留最近 n 条消息不参与压缩

        Returns:
            是否成功
        """
        session = await self.get_session(session_id)
        if not session:
            logging.warning("Cannot compact: session not found: %s", session_id)
            return False
        ok = await SessionCompaction.compact(session, keep_last_n=keep_last_n)
        if not ok:
            return False
        session.last_updated = datetime.now()
        await self._store.save(session)
        logging.info("Compacted session %s (keep_last_n=%d)", session_id, keep_last_n)
        return True

    async def prune_session(self, session_id: str) -> int:
        """对会话执行 prune：标记旧 tool result 输出为已清空（不删历史）。"""
        session = await self.get_session(session_id)
        if not session:
            logging.warning("Cannot prune: session not found: %s", session_id)
            return 0
        pruned_tokens = SessionCompaction.prune(session)
        if pruned_tokens <= 0:
            return 0
        session.last_updated = datetime.now()
        await self._store.save(session)
        logging.info("Pruned session %s (tokens=%d)", session_id, pruned_tokens)
        return pruned_tokens


SESSION_MANAGER = SessionManager()

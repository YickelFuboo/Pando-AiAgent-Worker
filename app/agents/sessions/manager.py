import asyncio
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any
from .message import Message
from .models import SessionRecord
from .session import Session
from app.config.settings import settings
from app.infrastructure.database import get_db


class SessionStore(ABC):
    """会话存储抽象：仅暴露 get / save / delete，列表由 get_all 提供。"""

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Session]:
        """按 ID 获取会话。"""

    @abstractmethod
    async def save(self, session: Session) -> None:
        """保存或更新会话。"""

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除会话，返回是否成功。"""

    @abstractmethod
    async def get_all(self) -> List[Session]:
        """返回当前全部会话列表（文件存储用内部缓存，DB 直接查库）。"""


class LocalFileSessionStore(SessionStore):
    """本地文件存储：目录下 {session_id}.json，用 _cache 存 load 结果，仅暴露 get/save/delete。"""

    def __init__(self) -> None:
        self.storage_dir = settings.agent_session_storage_dir
        self._cache: Dict[str, Session] = {}

    def _load_one(self, session_id: str) -> Optional[Session]:
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session(**data)
        except Exception as e:
            logging.error("Error loading session %s: %s", session_id, e)
            return None

    async def get(self, session_id: str) -> Optional[Session]:
        if session_id in self._cache:
            return self._cache[session_id]
        data = await asyncio.to_thread(self._load_one, session_id)
        if data:
            self._cache[session_id] = data
        return data

    async def save(self, session: Session) -> None:
        path = os.path.join(self.storage_dir, f"{session.session_id}.json")
        try:
            data = session.model_dump()

            def write_file():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            await asyncio.to_thread(write_file)
            self._cache[session.session_id] = session
        except Exception as e:
            logging.error("Error saving session %s: %s", session.session_id, e)

    async def delete(self, session_id: str) -> bool:
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        self._cache.pop(session_id, None)
        if not os.path.isfile(path):
            return False
        try:
            await asyncio.to_thread(os.remove, path)
            logging.info("Deleted session file: %s", session_id)
            return True
        except Exception as e:
            logging.error("Error deleting session %s: %s", session_id, e)
            return False

    async def get_all(self) -> List[Session]:
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir, exist_ok=True)
            logging.info("Created sessions directory: %s", self.storage_dir)
            return []
        self._cache.clear()
        for filename in os.listdir(self.storage_dir):
            if not filename.endswith(".json"):
                continue
            session_id = filename[:-5]
            path = os.path.join(self.storage_dir, filename)
            try:
                def read_file():
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                data = await asyncio.to_thread(read_file)
                self._cache[session_id] = Session(**data)
            except Exception as e:
                logging.error("Error loading session %s: %s", session_id, e)
        return list(self._cache.values())


def _row_to_session(row) -> Session:
    """将 SessionRecord 或 Row 转为 Session。注意：仅用 metadata_ 取元数据列，避免与 SQLAlchemy Base.metadata 冲突。"""
    msg_list = row.messages if isinstance(row.messages, list) else (json.loads(row.messages) if row.messages else [])
    messages = [Message(**m) for m in msg_list]
    meta = getattr(row, "metadata_", None)
    if meta is None or not isinstance(meta, dict):
        meta = {}
    return Session(
        session_id=row.session_id,
        description=row.description,
        session_type=row.session_type,
        user_id=row.user_id,
        llm_name=row.llm_name or "default",
        messages=messages,
        metadata=meta,
        created_at=row.created_at,
        last_updated=row.last_updated,
    )


class DatabaseSessionStore(SessionStore):
    """数据库存储：单表 agent_sessions，使用 get_db() 获取 session。"""

    async def get(self, session_id: str) -> Optional[Session]:
        from sqlalchemy import select
        async for db in get_db():
            r = (
                await db.execute(
                    select(SessionRecord).where(SessionRecord.session_id == session_id)
                )
            ).scalars().first()
            if not r:
                return None
            return _row_to_session(r)
        return None

    async def save(self, session: Session) -> None:
        from sqlalchemy import select
        messages_json = [msg.model_dump() for msg in session.messages]
        async for db in get_db():
            try:
                r = (
                    await db.execute(
                        select(SessionRecord).where(SessionRecord.session_id == session.session_id)
                    )
                ).scalars().first()
                if r:
                    rec = r
                    rec.description = session.description
                    rec.session_type = session.session_type
                    rec.user_id = session.user_id
                    rec.llm_name = session.llm_name
                    rec.messages = messages_json
                    rec.metadata_ = session.metadata
                    rec.last_updated = session.last_updated
                else:
                    db.add(SessionRecord(
                        session_id=session.session_id,
                        description=session.description,
                        session_type=session.session_type,
                        user_id=session.user_id,
                        llm_name=session.llm_name,
                        messages=messages_json,
                        metadata_=session.metadata,
                        created_at=session.created_at,
                        last_updated=session.last_updated,
                    ))
                await db.commit()
                logging.info("Session saved to database: %s", session.session_id)
            except Exception as e:
                await db.rollback()
                logging.error("Error saving session %s: %s", session.session_id, e)
                raise
            break

    async def delete(self, session_id: str) -> bool:
        from sqlalchemy import delete
        async for db in get_db():
            try:
                r = await db.execute(delete(SessionRecord).where(SessionRecord.session_id == session_id))
                await db.commit()
                return r.rowcount > 0
            except Exception as e:
                await db.rollback()
                logging.error("Error deleting session %s: %s", session_id, e)
                return False
            break
        return False

    async def get_all(self) -> List[Session]:
        from sqlalchemy import select
        result: List[Session] = []
        async for db in get_db():
            rows = (await db.execute(select(SessionRecord))).scalars().all()
            for row in rows:
                try:
                    result.append(_row_to_session(row))
                except Exception as e:
                    logging.error("Error deserializing session %s: %s", row.session_id, e)
            break
        return result


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
        session_type: str,
        user_id: str = "anonymous",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        llm_name: Optional[str] = None
    ) -> str:
        """创建新会话。DB 由 Store 内部管理，不由 API 注入。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        session_id = f"session_{timestamp}_{random_suffix}"
        session = Session(
            session_id=session_id,
            user_id=user_id,
            description=description,
            session_type=session_type,
            llm_name=llm_name or "default",
        )
        if metadata:
            for key, value in metadata.items():
                session.set_metadata(key, value)
        
        self.sessions[session_id] = session
        await self._store.save(session)

        logging.info("Created session: %s", session_id)
        return session_id

    async def add_message(self, session_id: str, message: Message) -> bool:
        """添加消息到会话"""
        session = await self.get_session(session_id)
        if not session:
            return False
        try:
            session.add_message(message)
            await self._store.save(session)
            return True
        except Exception as e:
            logging.error("Error adding message to session %s: %s", session_id, e)
            return False

    async def get_all_sessions(self) -> List[Session]:
        """获取所有会话。按需 get_all 并合并到缓存。"""
        all_sessions = await self._store.get_all()
        self.sessions.update({s.session_id: s for s in all_sessions})
        return list(self.sessions.values())

    async def get_sessions_by_type(self, session_type: str) -> List[Session]:
        """按会话类型获取会话"""
        all_sessions = await self._store.get_all()
        self.sessions.update({s.session_id: s for s in all_sessions})
        return [s for s in self.sessions.values() if s.session_type == session_type]

    async def get_sessions_by_user_id(self, user_id: str) -> List[Session]:
        """按用户ID获取会话"""
        all_sessions = await self._store.get_all()
        self.sessions.update({s.session_id: s for s in all_sessions})
        return [s for s in self.sessions.values() if s.user_id == user_id]

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
            session.messages.clear()
            session.last_updated = datetime.now()
            await self._store.save(session)
            logging.info("Cleared history for session: %s", session_id)
            return True
        except Exception as e:
            logging.error("Error clearing history for session %s: %s", session_id, e)
            return False


session_manager = SessionManager()

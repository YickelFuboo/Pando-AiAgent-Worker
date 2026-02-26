"""会话存储：本地文件与数据库两种实现。"""
import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from sqlalchemy import delete, select
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
    """本地文件存储：目录下 {session_id}.json，用 _cache 存 load 结果。"""

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
    llm_provider = getattr(row, "llm_provider", None) or ""
    last_consolidated = getattr(row, "last_consolidated", 0) or 0
    memory = getattr(row, "memory", None) or ""
    return Session(
        session_id=row.session_id,
        description=row.description,
        session_type=row.session_type,
        user_id=row.user_id,
        llm_provider=llm_provider,
        llm_name=row.llm_name or "default",
        messages=messages,
        metadata=meta,
        last_consolidated=last_consolidated,
        memory=memory,
        created_at=row.created_at,
        last_updated=row.last_updated,
    )


class DatabaseSessionStore(SessionStore):
    """数据库存储：单表 agent_sessions，使用 get_db() 获取 session。"""

    async def get(self, session_id: str) -> Optional[Session]:
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
                    rec.llm_provider = session.llm_provider or ""
                    rec.llm_name = session.llm_name
                    rec.metadata_ = session.metadata
                    rec.messages = messages_json
                    rec.last_consolidated = session.last_consolidated
                    rec.memory = session.memory or ""
                    rec.last_updated = session.last_updated
                else:
                    db.add(SessionRecord(
                        session_id=session.session_id,
                        description=session.description,
                        session_type=session.session_type,
                        user_id=session.user_id,
                        llm_provider=session.llm_provider or "",
                        llm_name=session.llm_name,
                        metadata_=session.metadata,
                        messages=messages_json,
                        last_consolidated=session.last_consolidated,
                        memory=session.memory or "",
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

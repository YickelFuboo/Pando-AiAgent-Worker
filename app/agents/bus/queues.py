import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from app.agents.sessions.manager import SESSION_MANAGER
from app.agents.core.react import ReActAgent


@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    agent_type: str
    channel_type: str  # telegram, discord, slack, whatsapp
    channel_id: str  # Channel identifier
    session_id: str  # Session identifier
    user_id: str  # User identifier
    content: str  # Message text
    llm_provider: str = ""
    llm_model: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data

@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    channel_type: str
    channel_id: str
    user_id: str
    session_id: str
    content: str
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


ChannelOutboundCallback = Callable[[OutboundMessage], None]
CHANNEL_OUTBOUND_CALLBACKS: Dict[str, ChannelOutboundCallback] = {}

SESSION_MAILBOX_MAXSIZE = 50
SESSION_IDLE_TTL_SEC = 1800
GLOBAL_RUN_CONCURRENCY = 32

class MessageBus:
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        # session mailbox/worker 模型：同一 session 串行、不同 session 并行
        # - _session_mailboxes: 每个 session 一个收件箱（队列），同 session 的 inbound 先进入该队列
        # - _session_workers: 每个 session 一个 worker 协程任务，循环消费 mailbox 并执行（天然串行）
        # - _session_last_active_at: 记录 session 最近一次收到消息的时间，用于 idle TTL 回收资源
        # - _session_lock: 保护上述 dict 的并发读写，避免并发分发时重复创建 mailbox/worker
        self._session_mailboxes: Dict[str, asyncio.Queue[InboundMessage]] = {}
        self._session_workers: Dict[str, asyncio.Task] = {}
        self._session_last_active_at: Dict[str, float] = {}
        self._session_lock = asyncio.Lock()
        self._global_run_semaphore = asyncio.Semaphore(GLOBAL_RUN_CONCURRENCY)

    async def push_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        await self.inbound.put(msg)

    async def pop_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def push_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def pop_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    async def pop_outbound_by_session_id(self, session_id: str) -> OutboundMessage:
        """只消费指定 session_id 的下一条出站消息（不匹配的放回队列末尾，阻塞直到有该 session 的消息）。"""
        while True:
            outbound_msg = await self.pop_outbound()
            if outbound_msg.session_id == session_id:
                return outbound_msg
            await self.outbound.put(outbound_msg)
    
    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    async def run(self) -> None:
        """Run the message bus：inbound 与 outbound 两路循环并发执行。"""
        await asyncio.gather(self._run_inbound_loop(), self._run_outbound_loop())

    async def _run_inbound_loop(self) -> None:
        """循环消费 inbound：按 session_id 路由到 mailbox，由各 session worker 串行执行。"""
        while True:
            inbound_msg = await self.pop_inbound()
            if not inbound_msg:
                continue
            try:
                await self._dispatch_inbound(inbound_msg)
            except Exception as e:
                logging.exception("MessageBus process inbound failed: %s", e)
                try:
                    await self.push_outbound(OutboundMessage(
                        channel_type=inbound_msg.channel_type,
                        channel_id=inbound_msg.channel_id,
                        user_id=inbound_msg.user_id,
                        session_id=inbound_msg.session_id,
                        content=f"Error: {e!s}",
                    ))
                except Exception as push_err:
                    logging.warning("Failed to push error outbound: %s", push_err)

    async def _dispatch_inbound(self, inbound_msg: InboundMessage) -> None:
        session_id = inbound_msg.session_id
        if not session_id:
            raise ValueError("Session ID is required")
        async with self._session_lock:
            mailbox = self._session_mailboxes.get(session_id)
            if mailbox is None:
                mailbox = asyncio.Queue(maxsize=SESSION_MAILBOX_MAXSIZE)
                self._session_mailboxes[session_id] = mailbox
            self._session_last_active_at[session_id] = asyncio.get_running_loop().time()
            worker = self._session_workers.get(session_id)
            if worker is None or worker.done():
                self._session_workers[session_id] = asyncio.create_task(self._run_session_worker(session_id))
        if mailbox.full():
            try:
                mailbox.get_nowait()
            except Exception:
                pass
        await mailbox.put(inbound_msg)

    async def _run_session_worker(self, session_id: str) -> None:
        while True:
            mailbox = self._session_mailboxes.get(session_id)
            if mailbox is None:
                return
            try:
                msg = await asyncio.wait_for(mailbox.get(), timeout=SESSION_IDLE_TTL_SEC)
            except asyncio.TimeoutError:
                async with self._session_lock:
                    last_active_at = self._session_last_active_at.get(session_id)
                    now = asyncio.get_running_loop().time()
                    if last_active_at is None or now - last_active_at >= SESSION_IDLE_TTL_SEC:
                        self._session_mailboxes.pop(session_id, None)
                        self._session_last_active_at.pop(session_id, None)
                        self._session_workers.pop(session_id, None)
                        return
                continue
            try:
                async with self._global_run_semaphore:
                    await self._handle_inbound(msg)
            except Exception as e:
                logging.exception("Session worker failed: session_id=%s err=%s", session_id, e)
                try:
                    await self.push_outbound(OutboundMessage(
                        channel_type=msg.channel_type,
                        channel_id=msg.channel_id,
                        user_id=msg.user_id,
                        session_id=msg.session_id,
                        content=f"Error: {e!s}",
                    ))
                except Exception:
                    pass

    async def _handle_inbound(self, inbound_msg: InboundMessage) -> None:
        """处理单条 inbound：更新 session 信息 + 复用/创建 agent 串行执行。"""
        session_id = inbound_msg.session_id
        if not session_id:
           raise ValueError("Session ID is required")
        
        session = await SESSION_MANAGER.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        metadata = dict(inbound_msg.metadata) if inbound_msg.metadata else {}
        await SESSION_MANAGER.update_session(
            session_id, 
            description=session.description if session.description else inbound_msg.content[:20],
            channel_type=inbound_msg.channel_type,
            agent_type=inbound_msg.agent_type,
            llm_provider=inbound_msg.llm_provider,
            llm_model=inbound_msg.llm_model,
            metadata=metadata,
        ) 

        agent = ReActAgent(
            agent_type=inbound_msg.agent_type,
            channel_type=inbound_msg.channel_type,
            channel_id=inbound_msg.channel_id,
            session_id=session_id,
            user_id=inbound_msg.user_id,
            content=inbound_msg.content,
            llm_provider=inbound_msg.llm_provider,
            llm_model=inbound_msg.llm_model)

        await agent.run(inbound_msg.content)

    async def _run_outbound_loop(self) -> None:
        """循环消费 outbound，按 channel_type 回调发送。"""
        while True:
            outbound_msg = await self.pop_outbound()
            callback = CHANNEL_OUTBOUND_CALLBACKS.get(outbound_msg.channel_type)
            if callback:
                callback(outbound_msg)
            else:
                logging.warning("No outbound callback for channel_type=%s", outbound_msg.channel_type)

MESSAGE_BUS = MessageBus()
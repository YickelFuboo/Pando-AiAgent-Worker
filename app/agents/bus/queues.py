import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict
from app.agents.core.react import ReActAgent
from app.agents.sessions.manager import SESSION_MANAGER


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

class MessageBus:
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

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
        """循环消费 inbound，处理并产生 outbound。单条处理异常不影响总线。"""
        while True:
            inbound_msg = await self.pop_inbound()
            if not inbound_msg:
                continue
            try:
                await self._process_message(inbound_msg)
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

    async def _run_outbound_loop(self) -> None:
        """循环消费 outbound，按 channel_type 回调发送。"""
        while True:
            outbound_msg = await self.pop_outbound()
            callback = CHANNEL_OUTBOUND_CALLBACKS.get(outbound_msg.channel_type)
            if callback:
                callback(outbound_msg)
            else:
                logging.warning("No outbound callback for channel_type=%s", outbound_msg.channel_type)

    async def _process_message(self, inbound_msg: InboundMessage) -> None:
        """Process an inbound message."""
        session_id = inbound_msg.session_id
        if not session_id:
           raise ValueError("Session ID is required")
        
        session = await SESSION_MANAGER.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        agent = ReActAgent(
            agent_name="ReActAgent", 
            agent_description="A ReAct agent", 
            agent_type=inbound_msg.agent_type,
            channel_type=inbound_msg.channel_type,
            channel_id=inbound_msg.channel_id,
            session_id=inbound_msg.session_id,
            workspace_index=inbound_msg.session_id,
            user_id=inbound_msg.user_id,
            llm_provider=inbound_msg.llm_provider,
            llm_model=inbound_msg.llm_model,
        )

        # 运行Agent
        result = await agent.run(inbound_msg.content)

        # 发送最终相应消息
        outbound_msg = OutboundMessage(
            channel_type=inbound_msg.channel_type,
            channel_id=inbound_msg.channel_id,
            user_id=inbound_msg.user_id,
            session_id=inbound_msg.session_id,
            content=result,
        )
        await self.push_outbound(outbound_msg)


MESSAGE_BUS = MessageBus()
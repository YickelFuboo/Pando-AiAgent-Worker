"""会话压缩：当 token 接近上下文上限时，用摘要替代长历史。"""
import logging
import time
from typing import List,Optional
from app.agents.sessions.message import Message,Role
from app.agents.sessions.session import Session
from app.config.settings import settings
from app.infrastructure.llms.chat_models.factory import llm_factory
from app.infrastructure.llms.chat_models.schemes import TokenUsage
from app.infrastructure.llms.utils import num_tokens_from_string
from app.agents.sessions.manager import SESSION_MANAGER


class SessionCompaction:
    COMPACTION_BUFFER = 20_000
    COMPACTION_PROMPT = """Provide a detailed prompt for continuing our conversation above.
Focus on information that would be helpful for continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're going to do next.
The summary that you construct will be used so that another agent can read it and continue the work.

When constructing the summary, try to stick to this template:
---
## Goal

[What goal(s) is the user trying to accomplish?]

## Instructions

- [What important instructions did the user give you that are relevant]
- [If there is a plan or spec, include information about it so next agent can continue using it]

## Discoveries

[What notable things were learned during this conversation that would be useful for the next agent to know when continuing the work]

## Accomplished

[What work has been completed, what work is still in progress, and what work is left?]

## Relevant files / directories

[Construct a structured list of relevant files that have been read, edited, or created that pertain to the task at hand. If all the files in a directory are relevant, include the path to the directory.]
---"""


    @staticmethod
    def is_overflow(
        *,
        usage: TokenUsage,
        llm: Optional[object] = None,
    ) -> bool:
        """判断当前 token 数是否接近上下文上限，需要触发压缩。

        Args:
            tokens: 当前轮次的总 token 数（input + output 或 total）
            llm: 当前使用的 LLM 实例，用于读取模型配置（context_limit/max_tokens）

        Returns:
            True 表示溢出，应触发压缩
        """
        if not getattr(settings, "compaction_auto", True):
            return False
        
        llm_context_limit = None
        llm_max_output_tokens = None
        if llm is not None:
            limits = getattr(llm, "limits", None)
            llm_context_limit = getattr(limits, "context_limit", None)
            llm_max_output_tokens = getattr(limits, "max_output_tokens", None)

        limit = llm_context_limit or getattr(settings, "compaction_context_limit", 128_000)
        if limit <= 0:
            return False
        
        max_out = llm_max_output_tokens or 8192
        res = getattr(settings, "compaction_reserved", None)
        if res is None:
            res = min(SessionCompaction.COMPACTION_BUFFER, max_out)
        usable = limit - max_out - res  # 可用空间 = 上下文上限 - 下轮最大输出 token 数 - 为压缩预留的 token 缓冲
        if usable <= 0:
            return False
        return usage.overflow_basis() >= usable  # 当前模型交互 token 数是否超过可用空间


    @staticmethod
    async def compact(
        session: Session,
        keep_last_n: int = 0,
    ) -> bool:
        """对会话执行压缩（对外唯一入口）。

        行为：
        - 从 session.messages 中选取要压缩的历史（保留最近 keep_last_n 条不参与压缩）；
        - 使用 session.llm_provider/session.llm_model 创建 LLM 实例；
        - 调用模型生成摘要（assistant 消息）；
        - 调用 apply_compaction_to_session 写回 session.compaction 与 session.last_compacted。

        Returns:
            是否成功生成并写回摘要
        """
        msgs = session.messages
        if not msgs:
            return True
        compact_until = max(0, len(msgs) - max(0, keep_last_n))
        to_summarize = msgs[:compact_until]
        if not to_summarize:
            return True
        
        llm = llm_factory.create_model(provider=session.llm_provider, model=session.llm_model)
        try:
            summary_message = await SessionCompaction.compact_messages(llm=llm,messages=to_summarize)
            if summary_message is None or not (summary_message.content or "").strip():
                logging.warning("Compaction produced empty or failed summary for session %s", session.session_id)
                return False
            SessionCompaction.apply_compaction_to_session(session, summary_message, keep_last_n=keep_last_n)
            return True
        except Exception as e:
            logging.error("Compaction failed for session %s: %s", session.session_id, e)
            return False

    @staticmethod
    async def compact_messages(*, llm:object, messages:List[Message])->Optional[Message]:
        """生成会话摘要：使用 LLM 生成会话摘要。"""
        if not messages:
            return None
        history=[m.to_context() for m in messages]
        compact_system="You are a session summarization agent. Summarize the conversation concisely."
        response, usage = await llm.chat(
            system_prompt=compact_system,
            user_prompt="",
            user_question=SessionCompaction.COMPACTION_PROMPT,
            history=history,
            temperature=0.3,
        )
        if not response or not response.success or not response.content:
            return None
        return Message(role=Role.ASSISTANT,content=response.content.strip())

    @staticmethod
    def apply_compaction_to_session(
        session: Session,
        summary_message: Message,
        keep_last_n: int = 0,
    ) -> None:
        """将摘要应用到会话：保留全部历史，将摘要记录到 session.compaction，并更新 last_compacted。

        Args:
            session: 会话对象，会被原地修改（不会删除旧历史）
            summary_msg: 压缩生成的摘要消息
            keep_last_n: 保留最近 n 条消息不参与压缩（last_compacted 指向这些消息之前）
        """
        msgs = session.messages
        if not msgs:
            session.compaction = summary_message
            session.last_compacted = 0
            return
        compact_until = max(0, len(msgs) - max(0, keep_last_n))
        session.compaction = summary_message
        session.last_compacted = compact_until

    @staticmethod
    async def prune(session_id: str) -> int:
        """修剪会话历史：移除旧工具输出，保护最近工具输出窗口。
            此处仅为Message打上pruned_at时间戳，后续构造context时根据该时间戳修剪旧工具提供给模型的内容。
        """
        if not getattr(settings, "compaction_prune", True):
            return 0

        session = await SESSION_MANAGER.get_session(session_id)
        if not session:
            return 0

        protect = int(getattr(settings, "compaction_prune_protect", 40_000) or 40_000)
        minimum = int(getattr(settings, "compaction_prune_minimum", 20_000) or 20_000)
        protected_tools_raw = getattr(settings, "compaction_prune_protected_tools", "skill") or "skill"
        protected_tools = {t.strip() for t in protected_tools_raw.split(",") if t.strip()}

        candidates: List[Message] = []
        candidates_tokens = 0
        seen_tokens = 0

        start = session.last_compacted if (session.compaction is not None and session.last_compacted > 0) else 0
        scan = session.messages[start:]
        for msg in reversed(scan):
            if not msg.is_tool_result:
                continue
            if isinstance(msg.metadata, dict) and msg.metadata.get("pruned_at"):
                break
            if msg.name in protected_tools:
                continue
            t = num_tokens_from_string(msg.content or "")
            seen_tokens += t
            if seen_tokens <= protect:
                continue
            candidates.append(msg)
            candidates_tokens += t

        if candidates_tokens < minimum:
            return 0

        now_ms = int(time.time() * 1000)
        for msg in candidates:
            meta = msg.metadata if isinstance(msg.metadata, dict) else {}
            meta["pruned_at"] = now_ms
            msg.metadata = meta
        return candidates_tokens


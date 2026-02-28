from ast import Str
import base64
import mimetypes
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from ..prompts.prompt_template_load import get_prompt_template
from ..sessions.session import Session
from ..skills.manager import SkillsManager
from ..memorys.manager import MemoryManager


# 工作区根目录下会被读入 system prompt 的引导文件名（按顺序，存在则读）
AGENT_CONTEXT_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "RUNTIME.md"]
WORKSPACE_CONTEXT_FILES = ["MEMORY.md", "HISTORY.md"]

class ContextBuilder:

    def __init__(self, session: Session, agent_path: str, workspace_path: str, *kwargs: Any):
        self.session = session
        self.agent_path = agent_path
        self.workspace_path = workspace_path
        self.kwargs = kwargs
        self.skills_manager = SkillsManager(agent_path, workspace_path)
        self.memory_manager = MemoryManager(session, agent_path, workspace_path)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        拼出完整的 system prompt 字符串。
        顺序：身份与约定 → 引导文件 → 记忆 → 常驻技能全文 → 技能摘要（提示用 read_file 按需读）。
        """
        parts = []

        # 获取相关词参数
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        workspace_path = str(Path(self.workspace_context_dir).expanduser().resolve())
        agent_path = str(Path(self.agent_context_dir).expanduser().resolve())

        kwargs = {
            "runtime": runtime,
            "workspace_path": workspace_path
        }

        # 1. 构造Agent类型对应的引导文件
        for filename in AGENT_CONTEXT_FILES:
            file_path = self.agent_dir / filename
            if file_path.exists():
                content = get_prompt_template(agent_path, filename, kwargs)
                parts.append(f"{content}")

        # 2. 长期记忆：包装成 ## Long-term Memory
        memory = self.memory_manager.append_all_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        # 4. 技能分两种：常驻技能直接全文放入；其余只给摘要，让 Agent 用 read_file 按需读 SKILL.md
        always_skills = self.skills_manager.get_always_skills()
        if always_skills:
            always_content = self.skills_manager.get_skills_content_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills_manager.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        # 用分隔符连接各段，避免挤在一起
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _inject_runtime_context(
        user_content: str | list[dict[str, Any]],
        channel: str | None,
        chat_id: str | None,
    ) -> str | list[dict[str, Any]]:
        """
        在当前用户消息末尾追加「运行时上下文」：当前时间、时区、channel、chat_id。
        - 若 user_content 是字符串：直接拼在后面。
        - 若是多模态列表（如图+文）：追加一个 text 块，保证 LLM 能看到时间与来源。
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        block = "[Runtime Context]\n" + "\n".join(lines)
        if isinstance(user_content, str):
            return f"{user_content}\n\n{block}"
        return [*user_content, {"type": "text", "text": block}]
    
    def _load_bootstrap_files(self) -> str:
        """从工作区按 BOOTSTRAP_FILES 顺序读取存在的文件，拼成 ## 文件名 + 内容，不存在则跳过。"""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = Path(self.workspace) / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        拼出本次调用 LLM 的完整消息列表：system + history + 当前用户消息（含可选媒体与运行时上下文）。
        AgentLoop 每轮会先调用本方法得到 messages，再交给 provider.chat(messages, ...)。
        """
        messages = []

        # 第一条：系统提示（身份、引导文件、记忆、技能）
        system_prompt = self.build_system_prompt(skill_names)
        messages.append({"role": "system", "content": system_prompt})

        # 中间：历史对话（来自 Session，可能已截断或从 last_consolidated 起）
        messages.extend(history)

        # 最后一条：当前用户输入（支持多模态图片）+ 末尾注入时间、channel、chat_id
        user_content = self._build_user_content(current_message, media)
        user_content = self._inject_runtime_context(user_content, channel, chat_id)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """
        把当前用户消息做成 LLM 可用的 content：无媒体则返回纯文本；
        有媒体则只处理图片，转成 base64 data URL，与文本组成多模态列表（先图后文）。
        """
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        在 messages 末尾追加一条 role=tool 的消息（OpenAI 格式），
        表示某次工具调用的返回值，供下一轮 LLM 根据结果继续推理或回复。
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages
    
    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        在 messages 末尾追加一条 role=assistant 的消息。
        content 必填（部分厂商不允许缺少 content 键）；tool_calls 为 LLM 返回的本次工具调用；
        reasoning_content 为思考链输出，供 Kimi、DeepSeek-R1 等思考模型使用。
        """
        msg: dict[str, Any] = {"role": "assistant"}

        # 必须带上 content 键，否则部分 Provider（如 StepFun）会报错
        msg["content"] = content

        if tool_calls:
            msg["tool_calls"] = tool_calls

        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages
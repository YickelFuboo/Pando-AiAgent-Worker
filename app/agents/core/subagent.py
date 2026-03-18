import json
import logging
import uuid
import asyncio
from abc import ABC
from typing import Any, Dict, List, Optional, Tuple
from app.agents.bus.queues import MESSAGE_BUS
from app.agents.bus.types import InboundMessage
from app.agents.core.base import AgentState, ToolChoice
from app.agents.sessions.compaction import SessionCompaction
from app.agents.tools.factory import ToolsFactory
from app.agents.sessions.message import Message, Role, ToolCall, Function
from app.agents.sessions.session import Session
from app.infrastructure.llms.chat_models.factory import llm_factory
from app.infrastructure.llms.chat_models.schemes import TokenUsage
from app.agents.tools.local.file_system import ReadFileTool, WriteFileTool
from app.agents.tools.local.dir_operator import ListDirTool
from app.agents.tools.local.shell import ExecTool
from app.agents.tools.local.web import WebSearchTool, WebFetchTool
from app.agents.tools.local.file_system import ReleaseFileTextTool, InsertFileTool


class SubAgentManager(ABC):
    """SubAgent 管理器"""
    
    def __init__(
        self,
        user_id: str,
        parent_agent_type: str,
        session_id: str,
        channel_type: str,
        channel_id: str,
        workspace_path: str,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ):

        # 基本信息
        self.user_id = user_id
        self.parent_agent_type = parent_agent_type
        self.session_id = session_id
        self.channel_type = channel_type
        self.channel_id = channel_id
        self.workspace_path = workspace_path

        # 模型信息
        self.llm_provider = llm_provider or ""
        self.llm_model = llm_model or ""
        self.temperature = temperature or 0.7

        self.params = kwargs

        # 运行任务信息
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def start_task(
        self,
        task: str,
        label: str | None = None,
    ) -> str:
        """
        创建异步任务并登记，任务结束时从 _running_tasks 移除。返回「已启动」类提示。
        """
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")

        subagent = SubAgent(
            user_id=self.user_id,
            session_id=self.session_id,
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            workspace_path=self.workspace_path,
            parent_agent_type=self.parent_agent_type,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            temperature=self.temperature,
            **self.params,
        )
        
        bg_task = asyncio.create_task(
            subagent.run(task_id, task, display_label)
        )
        self._running_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))

        logging.info("Started subagent [{}]: {}", task_id, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."


class SubAgent(ABC):
    """SubAgent 执行类，属性仅在 __init__ 内通过 self 赋值。"""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        channel_type: str,
        channel_id: str,
        workspace_path: str,
        parent_agent_type: str,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ):

        # 基本信息
        self.user_id = user_id
        self.session_id = session_id
        self.channel_type = channel_type
        self.channel_id = channel_id
        self.workspace_path = workspace_path
        self.parent_agent_type = parent_agent_type

        # 提示词信息
        self.system_prompt = "You are subagent, a helpful assistant."
        self.user_prompt = ""
        self.next_step_prompt = "Please continue your work."

        # 模型信息
        self.llm_provider = llm_provider or ""
        self.llm_model = llm_model or ""
        self.temperature = temperature or 0.7

        self.params = kwargs

        # 执行步数相关
        self._state = AgentState.IDLE
        self._current_step = 0
        self._max_steps = 20
        self._max_duplicate_steps = 2   # 最大重复次数，用于检验当前项agent是否挂死

        # 工具信息
        self.available_tools = ToolsFactory(workspace_path=self.workspace_path)
        self.tool_choices = ToolChoice.AUTO
        self._register_tools()
        self.history_messages: List[Message] = []
        self.compaction: Optional[Message] = None
        self.last_compacted: int = 0

    def reset(self):
        """重置 agent 状态到初始状态
        
        重置以下内容：
        - 状态设置为 IDLE
        - 当前步数归零
        """
        try:
            self._state = AgentState.IDLE
            self._current_step = 0
            self.history_messages = []
            self.compaction = None
            self.last_compacted = 0
        except Exception as e:
            logging.error(f"Error in agent reset: {str(e)}")
            raise e

    def _register_tools(self) -> None:
        """SubAgent 仅注册文件/执行/搜索等工具，不注册 SpawnTool（子 Agent 不可再派生子任务）。"""
        self.available_tools.register_tools(
            ReadFileTool(),
            WriteFileTool(),
            ReleaseFileTextTool(),
            InsertFileTool(),
            ListDirTool(),
            ExecTool(),
            WebSearchTool(),
            WebFetchTool()
        )

    def _build_subagent_prompt(self) -> str:
        """子 Agent 专用 system prompt：身份、当前时间、能做/不能做、workspace 路径（具体任务由 question 传入）。"""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        return f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace
- Execute shell commands
- Search the web and fetch web pages
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history

## Workspace
Your workspace is at: {self.workspace_path}

When you have completed the task, provide a clear summary of your findings or actions."""

    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy"""
        stuck_prompt = "\
        Observed duplicate responses. Consider new strategies and avoid repeating ineffective paths already attempted."
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logging.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")

    async def is_stuck(self) -> bool:
        """Check if the agent is stuck in a loop by detecting duplicate content in history_messages."""
        if len(self.history_messages) < 2:
            return False
        last_message = self.history_messages[-1]
        if not (last_message.content or "").strip():
            return False
        duplicate_count = sum(
            1
            for msg in reversed(self.history_messages[:-1])
            if msg.role == Role.ASSISTANT and (msg.content or "") == (last_message.content or "")
        )
        return duplicate_count >= self._max_duplicate_steps

    async def run(self, task_id: str, task: str, label: str) -> None:
        """Run the agent
        
        Args:
            task_id: Task ID
            label: Label for the task
            task: Input task
            
        Returns:
            None
        """
        # 检查并重置状态
        if self._state != AgentState.IDLE:
            logging.warning(f"Agent is busy with state {self._state}, resetting...")
            self.reset()
        
        # 设置运行状态
        self._state = AgentState.RUNNING

        original_task = task
        llm = llm_factory.create_model(provider=self.llm_provider, model=self.llm_model)
        try:
            # 构建提示词
            self.system_prompt = self._build_subagent_prompt()

            content = ""
            is_add_user_message = False
            context_overflow_recovered = False
            while (self._current_step < self._max_steps and self._state != AgentState.FINISHED):
                self._current_step += 1

                # 模型思考和工具调度
                content, tool_calls, usage = await self.think(llm, task)
                if tool_calls:
                    if not is_add_user_message:
                        self.history_messages.append(Message.user_message(original_task))
                        is_add_user_message = True
                    self.history_messages.append(Message.tool_call_message(content, tool_calls))
                    await self.act(tool_calls)
                else:
                    if not is_add_user_message:
                        self.history_messages.append(Message.user_message(original_task))
                        is_add_user_message = True
                    if self._is_context_overflow_content(content) and not context_overflow_recovered:
                        await self._handle_context_overflow(usage, llm, force=True)
                        context_overflow_recovered = True
                        continue
                    self.history_messages.append(Message.assistant_message(content))
                    break

                await self._handle_context_overflow(usage, llm)

                # 检查模型是否进行死循环
                if await self.is_stuck():
                    self.handle_stuck_state()

                # 继续下一步
                task = self.next_step_prompt

            # 检查终止原因并重置状态
            if self._current_step >= self._max_steps:
                content += f"\n\n Terminated: Reached max steps ({self._max_steps})"
     
            await self._announce_result(task_id, label, original_task, content, True)
        except Exception as e:
            self._state = AgentState.ERROR
            self.history_messages.append(Message.assistant_message(f"Error in agent execution: {str(e)}"))
            await self._announce_result(task_id, label, original_task, f"Error in agent execution: {str(e)}", False)
        finally:
            self.reset()

    async def think(self, llm: Any, task: str) -> Tuple[str, List[ToolCall], TokenUsage]:
        """Think about the question"""
        history = self._build_session_for_context()

        response = None
        tool_calls = []
        try:
            if self.tool_choices == ToolChoice.NONE:
                response, usage = await llm.chat(
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=task,
                    history=history,
                    temperature=self.temperature,
                )
                if not response.success:
                    raise Exception(response.content)
            else:
                response, usage = await llm.ask_tools(
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=task,
                    history=history,
                    tools=self.available_tools.to_params(),
                    tool_choice=self.tool_choices.value,
                    temperature=self.temperature,
                )
                
                # 处理工具调用
                if response.tool_calls:
                    for i, tool_info in enumerate(response.tool_calls):
                        if tool_info.name:
                            tool_call = ToolCall(
                                id=tool_info.id,
                                function=Function(
                                    name=tool_info.name,
                                    arguments=json.dumps(tool_info.args, ensure_ascii=False)
                                )
                            )
                            tool_calls.append(tool_call)

                if not tool_calls and self.tool_choices == ToolChoice.REQUIRED:
                    raise ValueError("Tool calls required but none provided")

            return response.content, tool_calls, usage

        except Exception as e:
            logging.error(f"Error in subagent think process: %s", e)
            raise RuntimeError(str(e))

    async def act(self, tool_calls: List[ToolCall]) -> None:
        """Execute tool calls and handle their results"""
        try:
            for toolcall in tool_calls:
                content, meta = await self.execute_tool(toolcall)
                self.history_messages.append(
                    Message.tool_result_message(content, toolcall.function.name, toolcall.id, metadata=meta)
                )
        except Exception as e:
            logging.error(f"Error in subagent act process: %s", e)
            raise RuntimeError(str(e))

    async def execute_tool(self, toolcall: ToolCall) -> Tuple[str, Optional[Dict[str, Any]]]:
        """执行单次工具调用"""
        if not toolcall or not toolcall.function:
            raise ValueError("Invalid tool call format")
            
        name = toolcall.function.name
        if not self.available_tools.get_tool(name):
            raise ValueError(f"Unknown tool '{name}'")
            
        try:
            args = json.loads(toolcall.function.arguments or "{}")
            tool_result = await self.available_tools.execute(tool_name=name, tool_params=args)
            return (f"{tool_result.result}", getattr(tool_result, "metadata", None))
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON arguments for tool '{name}'")
            raise ValueError(f"Invalid JSON arguments for tool '{name}'")
        except Exception as e:
            logging.error(f"Tool({name}) execution error: {str(e)}")
            raise RuntimeError(f"Tool({name}) execution error: {str(e)}") 
    
    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        status: bool,
    ) -> None:
        """将子任务结果拼成一段说明（含「用 1～2 句自然总结」的提示），以 InboundMessage(channel=system, chat_id=origin_channel:origin_chat_id) 发到总线，主 Agent 会当 system 消息处理并回复用户。"""
        status_text = "completed successfully" if status else "failed"

        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

        inbound_msg = InboundMessage(
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            user_id=self.user_id,
            session_id=self.session_id,
            agent_type=self.parent_agent_type,
            content=announce_content,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
        )
        await MESSAGE_BUS.push_inbound(inbound_msg)
        logging.debug("Subagent [{}] announced result to {}:{}", task_id, self.channel_type, self.channel_id)

    def _is_context_overflow_content(self, content: str) -> bool:
        if not content:
            return False
        return "context_overflow" in content.lower()

    def _build_session_for_context(self) -> List[Dict[str, Any]]:
        context = Session(
            session_id=self.session_id,
            agent_type="SubAgent",
            user_id=self.user_id,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            messages=self.history_messages,
            compaction=self.compaction,
            last_compacted=self.last_compacted,
        ).to_context()
        return context

    async def _handle_context_overflow(self, usage: TokenUsage, llm: Any, force: bool = False) -> None:
        if SessionCompaction.is_overflow(usage=usage, llm=llm) or force:
            await self._compact_history(llm, keep_last_n=4)
        await self._prune_history()

    async def _compact_history(self, llm: Any, keep_last_n: int = 0) -> bool:
        if not self.history_messages:
            return True
        compact_until = max(0, len(self.history_messages) - max(0, keep_last_n))
        to_summarize = self.history_messages[:compact_until]
        if not to_summarize:
            return True
        summary_message = await SessionCompaction.compact(llm=llm, messages=to_summarize)
        if summary_message is None or not (summary_message.content or "").strip():
            return False
        self.compaction = summary_message
        self.last_compacted = compact_until
        return True

    async def _prune_history(self) -> int:
        start = self.last_compacted if (self.compaction is not None and self.last_compacted > 0) else 0
        scan = self.history_messages[start:]
        return SessionCompaction.prune(scan)
import json
from pydantic import BaseModel, Field
from abc import ABC
from typing import List, Dict, Any, Optional, Literal, Tuple    
from enum import Enum
from .session.manager import session_manager
from .session.models import Role, Message, ToolCall, Function
from .tools.base import BaseTool
from .tools.tools_factory import ToolsFactory
from .model import AgentState
from app.utils.logger import logger


class AgentState(str, Enum):
    """Agent state enumeration"""
    IDLE = "IDEL"  # Idle state
    RUNNING = "RUNNING"  # Running state
    WAITING = "WAITING"  # Waiting for user input
    ERROR = "ERROR"  # Error state
    FINISHED = "FINISHED"  # Finished state

class BaseAgent(BaseModel, ABC):
    """Base Agent class
    
    Base class for all agents, defining basic properties and methods.
    """
    # 基本信息
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    
    # 会话信息
    session_id: str = Field(..., description="Current session ID")
    parent_session_id: Optional[str] = Field(default=None, description="Parent session ID")
    
    # websocket用户连接信息
    client_id: str = Field(..., description="Client ID")

    # 提示词信息
    system_prompt: str = Field(..., description="System prompt")
    user_prompt: str = Field(..., description="User prompt")
    next_step_prompt: str = Field(..., description="Next step prompt")

    # 模型信息
    llm_provider: str = Field(..., description="LLM provider")
    llm_name: str = Field(..., description="LLM model name")

    # 工具信息
    available_tools: ToolsFactory = Field(default_factory=ToolsFactory, description="List of available tools")
    tool_choices: Literal["none", "auto", "required"] = "none"
    special_tool_names: List[str] = Field(default=None, description="Special tool names")
    tool_calls: Optional[List[ToolCall]] = None

    # 执行步数相关
    current_step: int = Field(default=0, description="Current step")
    max_steps: int = Field(default=50, description="Max steps")
    # 最大重复次数，用于检验当前项agent是否挂死
    max_duplicate_steps: int = 2

    state: AgentState = Field(default=AgentState.IDLE, description="Current agent state")
    
    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)

    def reset(self):
        """重置 agent 状态到初始状态
        
        重置以下内容：
        - 状态设置为 IDLE
        - 当前步数归零
        - 工具调用状态清空
        """
        try:
            self.state = AgentState.IDLE
            self.current_step = 0
            self.tool_calls = None
            logger.info(f"Agent state reset to IDLE")
        except Exception as e:
            logger.error(f"Error in agent reset: {str(e)}")
            raise e

    async def run(self, question: str) -> Dict[str, Any]:
        """Run the agent
        
        Args:
            question: Input question
            
        Returns:
            Dict[str, Any]: Execution result
        """        
        logger.info(f"Running agent {self.name} with question: {question}")

        if not self.llm_name or not self.session_id:
            raise ValueError("LLM name, session ID are required")
        
        # 检查并重置状态
        if self.state != AgentState.IDLE:
            logger.warning(f"Agent is busy with state {self.state}, resetting...")
            self.reset()
        
        try:
            # 设置运行状态
            self.state = AgentState.RUNNING
            logger.info(f"Agent state set to RUNNING")
            
            results = []
            while (self.current_step < self.max_steps and self.state != AgentState.FINISHED):
                self.current_step += 1
                logger.info(f"Executing step {self.current_step}/{self.max_steps}")

                # 更新历史记录
                await self.update_history(Message.user_message(question))

                # 执行模型分析和工具调度工作
                result_messages = await self.think_and_act(question)
                if self.is_stuck():
                    self.handle_stuck_state()

                # 添加当前think and action步骤入History
                #await self.update_history(Message.user_message(question))
                #for message in step_result:
                #    await self.update_history(message)

                # 把当前结果转换为文本，用户返回给用户、或主Agent最终结果
                # 样例：
                # Step 1: 在xx文件中新增xx/xxx/xxx API接口
                #   sub_step 1: 在xx文件中新增xx/xxx/xxx API接口
                #   sub_step 2: 在xx文件中新增xx/xxx/xxx API接口
                result = f"Step {self.current_step}: {question}\n"
                for i, message in enumerate(result_messages):
                    result += f"    sub_step{i+1}: {message.to_user_message().get('content')}\n"
                result += f"\n"             
                results.append(result)               

                question = self.next_step_prompt

            # 检查终止原因并重置状态
            if self.current_step >= self.max_steps:
                results.append(f"Terminated: Reached max steps ({self.max_steps})")
            elif self.state == AgentState.FINISHED:
                results.append("Task completed successfully")
            
            # 统一重置状态
            self.reset()
            return "\n".join(results) if results else "No steps executed"
                
        except Exception as e:
            # 发生错误时设置错误状态
            self.state = AgentState.ERROR
            logger.error(f"Error in agent execution: {str(e)}")
            raise e
    async def think_and_act(self, question: str) -> List[Message]:
        """Execute a single step: think and act."""
        logger.info(f"Thinking and acting for question: {question}")

        try:
            content, has_tools = await self.think(question)

            if not has_tools:
                message = Message.assistant_message(content)
                await self.update_history_and_push_user_message(message=message)
                return [message]
            else:
                message = Message.from_tool_calls(content=content, tool_calls=self.tool_calls)
                await self.update_history_and_push_user_message(message=message)

                # 执行工具调用
                tool_messages = await self.act()
                return [message, *tool_messages]
                                
        except Exception as e:
            logger.error(f"Error in {self.name}'s thinking process: {str(e)}")
            raise RuntimeError(str(e))

    async def think(self, question: str) -> Tuple[str, bool]:
        """Think about the question"""
        # 获取当前会话历史
        history = self.get_history()

        try:       
            if self.tool_choices == "none":
                response = await llm_factory.chat(
                    llm_name=self.llm_name,
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=question,
                    stream=False,
                    history=history
                )

                if not response.success:
                    raise Exception(response.content)
                
                has_tools = False
            else:
                # Get response with tool options
                response = await llm_factory.ask_tools(
                    llm_name=self.llm_name,
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=question,
                    stream=False,
                    history=history,
                    tools=self.available_tools.to_params(),
                    tool_choice=self.tool_choices,
                )
                
                # 处理工具调用
                if response.tool_calls:
                    # 处理工具调用列表
                    self.tool_calls = []
                    for i, tool_info in enumerate(response.tool_calls):
                        tool_call = ToolCall(
                            id=tool_info.id,
                            function=Function(
                                name=tool_info.name,
                                arguments=json.dumps(tool_info.args, ensure_ascii=False)
                            )
                        )
                        self.tool_calls.append(tool_call)
                    has_tools = True
                else:
                    # 如果没有工具调用
                    self.tool_calls = []
                    has_tools = False

                # 结果信息打印
                logger.info(f"{self.name}'s thoughts: {response.content}")
                logger.info(f"{self.name} selected {len(self.tool_calls)} tools to use")

                if not self.tool_calls and self.tool_choices == "required":
                    raise ValueError("Tool calls required but none provided")

            return response.content, has_tools

        except Exception as e:
            logger.error(f"Error in {self.name}'s thinking process: {str(e)}")
            raise RuntimeError(str(e))

    async def act(self) -> List[Message]:
        """Execute tool calls and handle their results"""
        result_messages = []
        for toolcall in self.tool_calls:
            # 通知用户工具执行中...
            await self.push_user_message(message=Message.assistant_message(
                content=f"**{toolcall.function.name}**...")
            )

            # 执行工具
            result = await self.execute_tool(toolcall)                        
            message = Message.tool_message(
                content=result,
                name=toolcall.function.name,
                tool_call_id=toolcall.id
            )
            result_messages.append(message)
            
            logger.info(f"Tool '{toolcall.function.name}' completed! Result: {result}")

            # 通知用户工具执行结果
            await self.update_history_and_push_user_message(message=message)

        return result_messages

    async def execute_tool(self, toolcall: ToolCall) -> str:
        """Execute a single tool call with robust error handling"""
        if not toolcall or not toolcall.function:
            raise ValueError("Invalid tool call format")
            
        name = toolcall.function.name
        if name not in self.available_tools._tools:
            raise ValueError(f"Unknown tool '{name}'")
            
        try:
            # Parse arguments
            args = json.loads(toolcall.function.arguments or "{}")

            tool_result = await self.available_tools.execute_tool(tool_name=name, tool_params=args)

            # 跟模工具执行结果更新Agent状态
            # 通知用户工具执行结果...
            if self._is_special_tool(name):
                await self._handle_special_tool(name)

            # 按照Message格式返回工具执行结果
            return f"{tool_result.result}"

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON arguments for tool '{name}'")
            raise ValueError(f"Invalid JSON arguments for tool '{name}'")
        except Exception as e:
            logger.error(f"Tool({name}) execution error: {str(e)}")
            raise RuntimeError(f"Tool({name}) execution error: {str(e)}") 
    
    async def _handle_special_tool(self, name: str, **kwargs):
        """Handle special tool execution and state changes"""
        self.state = AgentState.FINISHED
        logger.info(f"Task completion or phased completion by special tool '{name}'")

    def _is_special_tool(self, name: str) -> bool:
        """Check if tool name is in special tools list"""
        return name.lower() in [n.lower() for n in self.special_tool_names]
    
    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy"""
        stuck_prompt = "\
        Observed duplicate responses. Consider new strategies and avoid repeating ineffective paths already attempted."
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logger.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")

    def is_stuck(self) -> bool:
        """Check if the agent is stuck in a loop by detecting duplicate content"""
        history = self.get_history()
        if len(history) < 2:
            return False

        last_message = history[-1]
        if not last_message.content:
            return False

        # Count identical content occurrences
        duplicate_count = sum(
            1
            for msg in reversed(history[:-1])
            if msg.role == Role.ASSISTANT and msg.content == last_message.content
        )

        return duplicate_count >= self.max_duplicate_steps

    def get_state(self) -> AgentState:
        """Get current state
        
        Returns:
            AgentState: Current state
        """
        return self.state
        
    def get_available_tools(self) -> List[str]:
        """Get available tools list
        
        Returns:
            List[str]: List of available tools
        """
        return list(self.available_tools.keys())
        
    def add_tool(self, tool: BaseTool) -> None:
        """Add tool
        
        Args:
            tool_name: Tool name
        """
        if tool not in self.available_tools:
            self.available_tools.add_tool(tool)
            
    def remove_tool(self, tool: BaseTool) -> None:
        """Remove tool
        
        Args:
            tool_name: Tool name
        """
        if tool in self.available_tools:
            self.available_tools.remove_tool(tool)
    
    async def update_history(self, message: Message) -> None:
        """Update message history
        
        Args:
            message: Message to add
        """
        await session_manager.add_message(self.session_id, message)
    
    def get_history(self) -> List[Message]:
        """Get message history
        
        Returns:
            List[Message]: Message history
        """
        return session_manager.get_session(self.session_id).get_history_for_context()
    
    async def push_user_message(self, message: Message) -> bool:
        """Push user message to history"""
        # 发送工具调用结
        try:
            await websocket_manager.send_message(
                client_id=self.client_id,
                message=WebSocketMessage(
                    message_type=WebSocketMessageType.RESPONSE,
                    current_session_id=self.session_id,
                    content=message.to_user_message().get("content"),
                )
            )
            return True
        
        except Exception as e:
            logger.error(f"Error pushing user message: {str(e)}")
            return False
        
    async def update_history_and_push_user_message(self, message: Message) -> bool:
        """Update history and push user message to history"""
        try:
            await self.update_history(message)
            await self.push_user_message(message)
            return True
        
        except Exception as e:
            logger.error(f"Error updating history and pushing user message: {str(e)}")
            raise e
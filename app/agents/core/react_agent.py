import json
from pydantic import BaseModel, Field
from abc import ABC
from typing import List, Dict, Any, Optional, Literal, Tuple    
from enum import Enum
import logging
from app.agents.sessions.manager import SESSION_MANAGER
from app.agents.tools.base import BaseTool
from app.agents.tools.factory import ToolsFactory
from app.agents.core.base import BaseAgent, AgentState
from app.agents.sessions.models import Role, Message, ToolCall, Function
from app.infrastructure.llms.chat_models.factory import llm_factory

class ReActAgent(BaseAgent):

    # 工具信息
    available_tools: ToolsFactory = Field(default_factory=ToolsFactory, description="List of available tools")
    tool_choices: Literal["none", "auto", "required"] = "none"
    special_tool_names: List[str] = Field(default=None, description="Special tool names")
    tool_calls: Optional[List[ToolCall]] = None

    def __init__(
        self,
        name: str,
        description: str,
        session_id: str,
        workspace: str,
        system_prompt: str,
        user_prompt: str,
        next_step_prompt: str,
        llm_provider: str,
        llm_name: str,
        max_steps: int = 50,
        max_duplicate_steps: int = 2,
        available_tools: ToolsFactory = Field(default_factory=ToolsFactory, description="List of available tools"),
        tool_choices: Literal["none", "auto", "required"] = "none",
        **kwargs: Any,
    ):
        super().__init__(
            name=name,
            description=description,
            session_id=session_id,
            workspace=workspace,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            next_step_prompt=next_step_prompt,
            llm_provider=llm_provider,
            llm_name=llm_name,
            max_steps=max_steps,
            max_duplicate_steps=max_duplicate_steps,
            **kwargs,
        )
        self.available_tools = available_tools
        self.tool_choices = tool_choices
        # 特殊工具名称列表
        self.special_tool_names = ["terminate"]

    def reset(self):
        """重置 agent 状态到初始状态
        - 工具调用状态清空
        """
        super().reset()
        self.tool_calls = None
        self.tool_choices = "none"
        self.special_tool_names = None
        logging.info(f"ReActAgent state reset to IDLE")

    async def run(self, question: str) -> None:
        """Run the agent
        
        Args:
            question: Input question
            
        Returns:
            str: Execution result
        """        
        logging.info(f"Running agent {self.name} with question: {question}")

        if not self.session_id or not self.workspace:
            raise ValueError("Session ID and workspace are required")
        
        # 检查并重置状态
        if self.state != AgentState.IDLE:
            logging.warning(f"Agent is busy with state {self.state}, resetting...")
            self.reset()
        
        try:
            # 设置运行状态
            self.state = AgentState.RUNNING
            logging.info(f"Agent state set to RUNNING")
            
            while (self.current_step < self.max_steps and self.state != AgentState.FINISHED):
                self.current_step += 1
                logging.info(f"Executing step {self.current_step}/{self.max_steps}")

                # 更新历史记录
                await self.push_message(self.session_id, Message.user_message(question))

                # 执行模型分析和工具调度工作
                await self.think_and_act(question)
                if self.is_stuck():
                    self.handle_stuck_state()            

                # 继续下一步
                question = self.next_step_prompt

            # 检查终止原因并重置状态
            if self.current_step >= self.max_steps:
                result += f"\n\n Terminated: Reached max steps ({self.max_steps})"
                self.notify_user(self.session_id, Message.assistant_message(result))
     
            # 统一重置状态
            self.reset()
                
        except Exception as e:
            # 发生错误时设置错误状态
            self.state = AgentState.ERROR
            self.notify_user(self.session_id, Message.assistant_message(f"Error in agent execution: {str(e)}"))
            raise e

    async def think_and_act(self, question: str) -> None:
        """Execute a single step: think and act."""
        logging.info(f"Thinking and acting for question: {question}")

        try:
            content, has_tools = await self.think(question)
            if not has_tools:
                await self.push_history_message_and_notify_user(self.session_id, Message.assistant_message(content))
            else:
                await self.push_history_message_and_notify_user(self.session_id, Message.tool_call_message(content, self.tool_calls))    
                await self.act()
        
        except Exception as e:
            logging.error(f"Error in {self.name}'s thinking process: {str(e)}")
            raise RuntimeError(str(e))

    async def think(self, question: str) -> Tuple[str, bool]:
        """Think about the question"""
        # 获取当前会话历史
        history = await self.get_history_context(self.session_id)
        llm = llm_factory.create_model(
            provider=self.llm_provider,
            model=self.llm_name
        )
        try:
            if self.tool_choices == "none":
                response = await llm.chat(
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=question,
                    history=history
                )
                if not response.success:
                    raise Exception(response.content)
                
                has_tools = False
            else:
                # Get response with tool options
                response = await llm.ask_tools(
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    user_question=question,
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
                logging.info(f"{self.name}'s thoughts: {response.content}")
                logging.info(f"{self.name} selected {len(self.tool_calls)} tools to use")

                if not self.tool_calls and self.tool_choices == "required":
                    raise ValueError("Tool calls required but none provided")

            return response.content, has_tools

        except Exception as e:
            logging.error(f"Error in {self.name}'s thinking process: {str(e)}")
            raise RuntimeError(str(e))

    async def act(self) -> None:
        """Execute tool calls and handle their results"""
        try:
            for toolcall in self.tool_calls:
                # 通知用户工具执行中...
                await self.notify_user(self.session_id, Message.assistant_message(
                    content=f"calling tool: {toolcall.function.name}, parameters: {toolcall.function.arguments}")
                )

                # 执行工具
                result = await self.execute_tool(toolcall)  
                await self.push_history_message_and_notify_user(self.session_id, Message.tool_result_message(
                    result, toolcall.function.name, toolcall.id)
                )            
                logging.info(f"Tool '{toolcall.function.name}' completed! Result: {result}")
        
        except Exception as e:
            logging.error(f"Error in {self.name}'s act process: {str(e)}")
            raise RuntimeError(str(e))


    async def execute_tool(self, toolcall: ToolCall) -> str:
        """Execute a single tool call with robust error handling"""
        if not toolcall or not toolcall.function:
            raise ValueError("Invalid tool call format")
            
        name = toolcall.function.name
        if not self.available_tools.get_tool(name):
            raise ValueError(f"Unknown tool '{name}'")
            
        try:
            # Parse arguments
            args = json.loads(toolcall.function.arguments or "{}")

            tool_result = await self.available_tools.execute(tool_name=name, tool_params=args)

            # 跟模工具执行结果更新Agent状态
            if self._is_special_tool(name):
                await self._handle_special_tool(name)

            return f"{tool_result.result}"

        except json.JSONDecodeError:
            logging.error(f"Invalid JSON arguments for tool '{name}'")
            raise ValueError(f"Invalid JSON arguments for tool '{name}'")
        except Exception as e:
            logging.error(f"Tool({name}) execution error: {str(e)}")
            raise RuntimeError(f"Tool({name}) execution error: {str(e)}") 

    async def _handle_special_tool(self, name: str, **kwargs):
        """Handle special tool execution and state changes"""
        self.state = AgentState.FINISHED
        logging.info(f"Task completion or phased completion by special tool '{name}'")

    def _is_special_tool(self, name: str) -> bool:
        """Check if tool name is in special tools list"""
        return name.lower() in [n.lower() for n in self.special_tool_names]
        
    def get_available_tools(self) -> List[str]:
        """Get available tools list
        
        Returns:
            List[str]: List of available tools
        """
        return list(self.available_tools.keys())

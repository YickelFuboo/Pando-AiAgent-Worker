from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from app.agents.model import AgentType
from app.llms.factory import llm_factory
from app.llms.tokenizer import tokenizer
from .models import Message

class Session(BaseModel):
    """会话类"""
    session_id: str    
    description: Optional[str] = None
    agent_type: AgentType
    username: str
    created_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    
    # 模型配置
    llm_name: str = "default"  # 使用的模型名称
    
    # 消息历史
    # 原始完整消息，用于和用户交互展示
    original_messages: List[Message] = []  # 完整历史
    # 压缩历史，用于模型上下文
    compressed_messages: List[Message] = []  # 压缩历史    
    # Token计数
    current_tokens: int = 0  # 当前压缩历史的token总数
    
    # 会话元数据，用于存储不同类型会话的特定信息
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # 压缩状态
    compressing: bool = False
    last_compress_failed: Optional[datetime] = None  # 记录上次压缩失败时间
    compress_cooldown: int = 300  # 压缩失败后的冷却时间(秒)
        
    # 子会话管理
    is_master_session: bool = False
    parent_session_id: Optional[str] = None  # 父会话ID
    sub_session_ids: List[str] = Field(default_factory=list)  # 子会话ID列表

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化方法"""
        return {
            "session_id": self.session_id,
            "description": self.description,
            "agent_type": self.agent_type,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "llm_name": self.llm_name,
            "original_messages": [msg.model_dump() for msg in self.original_messages],
            "compressed_messages": [msg.model_dump() for msg in self.compressed_messages],
            "current_tokens": self.current_tokens,
            "metadata": self.metadata,
            "compressing": self.compressing,
            "last_compress_failed": self.last_compress_failed.isoformat() if self.last_compress_failed else None,
            "compress_cooldown": self.compress_cooldown,
            "is_master_session": self.is_master_session,
            "parent_session_id": self.parent_session_id,
            "sub_session_ids": self.sub_session_ids
        }
    
    async def add_message(self, message: Message):
        """添加新消息
        
        策略：
        1. 添加到原始历史
        2. 如果正在压缩,等待压缩完成
        3. 如果最近压缩失败,使用简单截取策略
        """
        
        # 添加到最新消息到记录中
        self.original_messages.append(message)
        self.compressed_messages.append(message)                
        self.last_updated = datetime.now()
        
        # 计算新消息的token数
        new_tokens = tokenizer.calculate_tokens(message.to_json())        
        self.current_tokens += new_tokens
        max_tokens = llm_factory.get_llm_config(self.llm_name, "max_context_tokens")
        
        # 检查是否需要压缩
        if self.current_tokens > max_tokens * 0.8:
            # 检查是否在冷却期
            if (self.last_compress_failed and 
                (datetime.now() - self.last_compress_failed).seconds < self.compress_cooldown):
                # 在冷却期内,使用简单截取策略
                self.compressed_messages = self.original_messages[-10:]
                self.current_tokens = tokenizer.calculate_tokens(
                    "\n".join(msg.to_json() for msg in self.compressed_messages)
                )
            elif not self.compressing:
                # 不在冷却期且没有压缩任务,执行压缩
                self.compressing = True
                try:
                    await self._compress_history()
                except Exception as e:
                    print(f"Compression failed: {e}")
                    self.last_compress_failed = datetime.now()
                    # 压缩失败时使用简单截取策略
                    self.compressed_messages = self.original_messages[-10:]
                    self.current_tokens = tokenizer.calculate_tokens(
                        "\n".join(msg.to_json() for msg in self.compressed_messages)
                    )
                finally:
                    self.compressing = False
            else:
                # 正在压缩中,等待完成
                while self.compressing:
                    await asyncio.sleep(0.1)
    async def _compress_history(self):
        """压缩会话历史"""
        recent_messages = self.original_messages[-10:]  # 保留最近10条
        older_messages = self.original_messages[:-10]  # 需要压缩的消息
        
        if not older_messages:
            self.compressed_messages = recent_messages
            # 重新计算token总数
            self.current_tokens = tokenizer.calculate_tokens(
                "\n".join(msg.to_json() for msg in recent_messages)
            )
            return
        
        # 计算最近消息的token数
        recent_text = "\n".join(msg.to_json() for msg in recent_messages)
        recent_tokens = tokenizer.calculate_tokens(recent_text)
        available_tokens = int(llm_factory.get_llm_config(self.llm_name, "max_tokens") * 0.8) - recent_tokens
        
        if available_tokens <= 0:
            self.compressed_messages = recent_messages[-5:]  # 保留最新的5条
            # 重新计算token总数
            self.current_tokens = tokenizer.calculate_tokens(
                "\n".join(msg.to_json() for msg in self.compressed_messages)
            )
            return
        
        # 将较早的消息分组压缩
        chunks = [older_messages[i:i+10] for i in range(0, len(older_messages), 10)]
        compressed = []
        current_tokens = recent_tokens  # 从最近消息的token数开始计算
        
        for chunk in chunks:
            # 构建要总结的消息文本
            # 仅从Content内容进行压缩
            messages_text = "\n".join(
                f"{msg.role}: {msg.content}" 
                for msg in chunk
            )
            summary = await self._compress_summary(messages_text)
            summary_tokens = tokenizer.calculate_tokens(summary)
            
            if current_tokens + summary_tokens > llm_factory.get_llm_config(self.llm_name, "max_tokens") * 0.8:
                break
            
            compressed.append(Message(
                role="system",
                content=summary
            ))
            current_tokens += summary_tokens
        
        # 更新压缩历史和token计数
        self.compressed_messages = compressed + recent_messages
        self.current_tokens = current_tokens

    async def _compress_summary(self, messages_text: str) -> str:
        """压缩消息总结
        
        Args:
            messages_text: 要总结的消息文本
            
        Returns:
            str: 压缩后的总结文本,保持原有的角色和内容格式
        """
        prompt = (
            "请总结以下对话，保持关键信息，使用简洁的语言表达。"
            "总结时请保持每条消息的角色前缀(user:/assistant:)格式。"
            "总结后的内容应该比原文更短，但保留重要的上下文信息：\n\n"
            f"{messages_text}"
        )
        
        response = await llm_factory.chat(
            llm_name=self.llm_name,
            system_prompt=(
                "你是一个专业的对话总结助手，善于提取关键信息并简洁表达。"
                "总结时需要保持原有的对话格式，即每条消息都带有角色前缀。"
            ),
            user_prompt="",
            user_question=prompt,
            stream=False
        )
        
        if not response.success:
            # 如果调用失败，返回一个简单的格式化消息
            return "assistant: 这是一段历史对话的总结 (包含多条消息)"
            
        # 确保返回的内容包含角色前缀
        content = response.content
        if not content.startswith(("user:", "assistant:", "system:")):
            content = f"assistant: {content}"
        
        return content

    def get_history_for_context(self) -> List[Message]:
        """获取用于模型上下文的历史
        
        返回 Message 对象列表，具体的格式转换由各个 LLM 实现类处理。
        即使压缩任务正在进行,也返回当前可用的历史。
        """
        return self.compressed_messages.copy()  # 返回副本以防止意外修改

    def to_info_summary(self) -> Dict[str, Any]:
        """获取会话基本信息(用于API返回)
        
        只返回用户界面需要的基本信息
        """
        info = {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "username": self.username,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "description": self.description,
            "llm_name": self.llm_name,
            "metadata": self.metadata,
            "parent_session_id": self.parent_session_id,
            "sub_session_ids": self.sub_session_ids
        }
            
        return info

    def to_info_detail(self) -> Dict[str, Any]:
        """获取会话详细信息(用于API返回)"""
        
        info = {
            "session_id": self.session_id,
            "agent_type": self.agent_type,
            "username": self.username,
            "llm_name": self.llm_name,
            "messages": [msg.to_user_message() for msg in self.original_messages],
            "metadata": self.metadata
        }
            
        return info

    def set_metadata(self, key: str, value: Any):
        """设置元数据"""
        self.metadata[key] = value
        
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)

    def add_sub_session(self, session_id: str) -> None:
        """添加子会话
        
        Args:
            session_id: 子会话ID
        """
        if session_id not in self.sub_sessions:
            self.sub_sessions.append(session_id)
            self.last_updated = datetime.now()
    
    def remove_sub_session(self, session_id: str) -> bool:
        """移除子会话
        
        Args:
            session_id: 子会话ID
            
        Returns:
            bool: 是否成功移除
        """
        if session_id in self.sub_sessions:
            self.sub_sessions.remove(session_id)
            self.last_updated = datetime.now()
            return True
        return False
    
    def get_sub_sessions(self) -> List[str]:
        """获取所有子会话ID列表"""
        return self.sub_sessions.copy()
    
    def set_parent_session(self, parent_id: str) -> None:
        """设置父会话ID
        
        Args:
            parent_id: 父会话ID
        """
        self.parent_session_id = parent_id
        self.last_updated = datetime.now()
    
    def get_parent_session(self) -> Optional[str]:
        """获取父会话ID"""
        return self.parent_session_id 


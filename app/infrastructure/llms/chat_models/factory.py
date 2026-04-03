from typing import Dict, Type
from .base import LLM
from .openai_llm import OpenAIModels
from .claude_llm import ClaudeModels
from .zhipu_llm import ZhiPuModels
from ..base_factory import BaseModelFactory

# =============================================================================
# 聊天模型工厂
# =============================================================================

class LLMFactory(BaseModelFactory):
    """聊天模型工厂类"""
    
    @property
    def _models(self) -> Dict[str, Type[LLM]]:
        return {
            "deepseek": OpenAIModels,
            "claude": ClaudeModels,
            "openai": OpenAIModels,
            "qwen": OpenAIModels,
            "siliconflow": OpenAIModels,
            "zhipu": ZhiPuModels,
        }
    
    def __init__(self):
        super().__init__("chat_models.json")
    

# 全局工厂实例
llm_factory = LLMFactory()
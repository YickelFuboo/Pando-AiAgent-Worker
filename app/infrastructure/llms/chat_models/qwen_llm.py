from openai import AsyncOpenAI
from app.infrastructure.llms.chat_models.base.openai_base import OpenAIBase
from app.infrastructure.llms.chat_models.base.base import build_llm_httpx_timeout

class QwenModels(OpenAIBase):
    """阿里云通义千问模型系列"""
    
    def __init__(self, api_key: str, model_name: str = "qwen-turbo", base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", language: str = "Chinese", **kwargs):
        """
        初始化Qwen模型
        
        Args:
            api_key (str): 阿里云API密钥
            model_name (str): 模型名称，默认为qwen-turbo
            base_url (str): API基础URL，默认为阿里云DashScope API
            language (str): 语言设置
            **kwargs: 其他参数
        """
        super().__init__(api_key, model_name, base_url, language, **kwargs)
        
        # 创建Qwen客户端（使用OpenAI兼容接口）
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=build_llm_httpx_timeout(**kwargs),
            max_retries=0,
        )

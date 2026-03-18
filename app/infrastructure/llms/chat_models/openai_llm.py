from openai import AsyncOpenAI
from app.infrastructure.llms.chat_models.base.openai_base import OpenAIBase
from app.infrastructure.llms.chat_models.base.base import build_llm_httpx_timeout

class OpenAIModels(OpenAIBase):
    """OpenAI模型系列"""
    
    def __init__(self, api_key: str, model_name: str = "gpt-4o", base_url: str = "https://api.openai.com/v1", language: str = "Chinese", **kwargs):
        """
        初始化OpenAI模型
        
        Args:
            api_key (str): OpenAI API密钥
            model_name (str): 模型名称，默认为gpt-4o
            base_url (str): API基础URL，默认为OpenAI官方API
            language (str): 语言设置
            **kwargs: 其他参数
        """
        super().__init__(api_key, model_name, base_url, language, **kwargs)
        
        # 创建OpenAI客户端
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=build_llm_httpx_timeout(**kwargs),
            max_retries=0,
        )

"""
大模型初始化模块

负责从 .env 中读取模型配置，并创建项目统一复用的模型对象
后续主智能体和子智能体都从这里导入 model，避免在多个文件里重复加载环境变量
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model

from app.config import get_settings


@lru_cache(maxsize=1)
def get_model():
    """Validate configuration and lazily create the shared chat model."""
    settings = get_settings()
    settings.validate_llm()
    return init_chat_model(model=settings.llm_name, model_provider="openai")

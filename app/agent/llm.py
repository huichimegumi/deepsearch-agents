"""
大模型初始化模块

负责从 .env 中读取模型配置，并创建项目统一复用的模型对象
后续主智能体和子智能体都从这里导入 model，避免在多个文件里重复加载环境变量
"""

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

from app.config import get_settings


class DeepSeekChatOpenAI(ChatOpenAI):
    """Use tool calling for structured output on DeepSeek's Chat Completions API."""

    def with_structured_output(self, schema=None, **kwargs):
        kwargs.setdefault("method", "function_calling")
        return super().with_structured_output(schema, **kwargs)


@lru_cache(maxsize=1)
def get_model():
    """Validate configuration and lazily create the shared chat model."""
    settings = get_settings()
    settings.validate_llm()
    model_kwargs = dict(
        model=settings.llm_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.tool_timeout_seconds,
        # Evaluation workers need one observable HTTP attempt per model invocation.
        max_retries=0 if os.getenv("EVAL_DISABLE_SDK_RETRIES") == "1" else 1,
    )
    if settings.llm_provider == "deepseek":
        # DeepSeek's thinking mode rejects the forced tool choice used by
        # LangChain's function-calling structured output.
        return DeepSeekChatOpenAI(
            **model_kwargs,
            extra_body={"thinking": {"type": "disabled"}},
        )
    return init_chat_model(model_provider="openai", **model_kwargs)

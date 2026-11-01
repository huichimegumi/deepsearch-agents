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


class EvaluationBudgetedChatOpenAI(ChatOpenAI):
    """Reserve an evaluation request before the OpenAI-compatible transport runs."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if os.getenv("EVAL_LEDGER_PATH"):
            from evals.request_budget import admit_request

            admit_request(payload)
        return payload


class DeepSeekChatOpenAI(EvaluationBudgetedChatOpenAI):
    """Use tool calling for structured output on DeepSeek's Chat Completions API."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # This OpenAI model adapter emits max_completion_tokens, while DeepSeek's
        # chat endpoint documents max_tokens. Without translation the cap is ignored.
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        return payload

    def with_structured_output(self, schema=None, **kwargs):
        kwargs.setdefault("method", "function_calling")
        return super().with_structured_output(schema, **kwargs)


class DashScopeChatOpenAI(EvaluationBudgetedChatOpenAI):
    """Send the output cap under DashScope's chat-completions field name."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        return payload


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
    if os.getenv("EVAL_TEMPERATURE") is not None:
        model_kwargs["temperature"] = float(os.environ["EVAL_TEMPERATURE"])
    if os.getenv("EVAL_DEFAULT_MAX_OUTPUT_TOKENS") is not None:
        model_kwargs["max_tokens"] = int(os.environ["EVAL_DEFAULT_MAX_OUTPUT_TOKENS"])
    if settings.llm_provider == "deepseek":
        # DeepSeek's thinking mode rejects the forced tool choice used by
        # LangChain's function-calling structured output.
        return DeepSeekChatOpenAI(
            **model_kwargs,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if settings.llm_provider == "dashscope":
        return DashScopeChatOpenAI(**model_kwargs)
    if os.getenv("EVAL_LEDGER_PATH"):
        return EvaluationBudgetedChatOpenAI(**model_kwargs)
    return init_chat_model(model_provider="openai", **model_kwargs)

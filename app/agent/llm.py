"""
大模型初始化模块

负责从 .env 中读取模型配置，并创建项目统一复用的模型对象
后续主智能体和子智能体都从这里导入 model，避免在多个文件里重复加载环境变量
"""

import os
from functools import lru_cache
from typing import ClassVar

from langchain_openai import ChatOpenAI

from app.config import get_settings


class EvaluationBudgetedChatOpenAI(ChatOpenAI):
    """Reserve an evaluation request before the OpenAI-compatible transport runs."""

    provider_uses_max_tokens: ClassVar[bool] = False

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if self.provider_uses_max_tokens and "max_completion_tokens" in payload:
            default_cap = payload.pop("max_completion_tokens")
            # A stage-bound max_tokens must win over the model's default cap.
            payload.setdefault("max_tokens", default_cap)
        from app.research.request_budget import admit_request

        admit_request(payload)
        from app.agent.runtime import get_research_budget
        from app.api.context import get_research_phase_context

        budget = get_research_budget()
        if (
            budget is not None
            and budget.admit_research_calls_before_transport
            and get_research_phase_context() == "supervisor_research"
            and not budget.take_llm_call("supervisor_research")
        ):
            from app.agent.main_agent import PhaseBudgetExceeded

            raise PhaseBudgetExceeded("llm_call_limit")
        return payload


class DeepSeekChatOpenAI(EvaluationBudgetedChatOpenAI):
    """Use tool calling for structured output on DeepSeek's Chat Completions API."""

    provider_uses_max_tokens: ClassVar[bool] = True

    def with_structured_output(self, schema=None, **kwargs):
        kwargs.setdefault("method", "function_calling")
        return super().with_structured_output(schema, **kwargs)


class DashScopeChatOpenAI(EvaluationBudgetedChatOpenAI):
    """Use compatible tool calling and output caps for DashScope."""

    provider_uses_max_tokens: ClassVar[bool] = True

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
        max_retries=0,
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
    return EvaluationBudgetedChatOpenAI(**model_kwargs)

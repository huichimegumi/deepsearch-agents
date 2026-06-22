"""Application-wide environment configuration and validation."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or "你的" in normalized
        or normalized.startswith("your_")
        or normalized in {"openai_api_key", "dashscope_api_key"}
    )


def _first_secret(*names: str) -> str:
    """Return the first real secret without treating variable names as values."""
    for name in names:
        value = os.getenv(name, "").strip()
        if not _is_placeholder(value):
            return value
    return ""


@dataclass(frozen=True)
class AppSettings:
    """Settings shared by the API and agent runtime."""

    llm_name: str
    openai_api_key: str
    openai_base_url: str | None
    cors_origins: tuple[str, ...]

    def validate_llm(self) -> None:
        missing = []
        if _is_placeholder(self.llm_name):
            missing.append("LLM_NAME")
        if _is_placeholder(self.openai_api_key):
            missing.append("OPENAI_API_KEY")
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(
                f"大模型配置无效或缺失: {names}。请复制 .env.example 为 .env 后填写真实配置。"
            )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings(
        llm_name=os.getenv("LLM_NAME", ""),
        openai_api_key=_first_secret("OPENAI_API_KEY", "DASHSCOPE_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        cors_origins=_split_csv(
            os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            )
        ),
    )

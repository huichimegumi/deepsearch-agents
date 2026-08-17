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
class AgentExecutionBudget:
    """Execution budget for one agent phase."""

    recursion_limit: int
    timeout_seconds: float


@dataclass(frozen=True)
class AppSettings:
    """Settings shared by the API and agent runtime."""

    llm_name: str
    openai_api_key: str
    openai_base_url: str | None
    cors_origins: tuple[str, ...]
    agent_recursion_limit: int = 30
    agent_max_runtime_seconds: float = 300.0
    agent_hard_max_recursion_limit: int = 160
    agent_hard_max_runtime_seconds: float = 1800.0
    agent_quick_slo_seconds: float = 60.0
    agent_standard_slo_seconds: float = 180.0
    agent_deep_slo_seconds: float = 300.0
    agent_thorough_slo_seconds: float = 900.0
    agent_phase_clarify_recursion_limit: int = 20
    agent_phase_clarify_timeout_seconds: float = 120.0
    agent_phase_research_recursion_limit: int = 90
    agent_phase_research_timeout_seconds: float = 900.0
    agent_phase_compression_recursion_limit: int = 40
    agent_phase_compression_timeout_seconds: float = 240.0
    agent_phase_final_report_recursion_limit: int = 60
    agent_phase_final_report_timeout_seconds: float = 420.0
    tool_timeout_seconds: float = 60.0
    db_timeout_seconds: int = 20
    db_table_preview_rows: int = 30
    db_query_preview_rows: int = 80
    db_max_result_chars: int = 12000
    rag_answer_max_hits: int = 6
    rag_answer_max_context_chars: int = 10000
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    allow_register: bool = True

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

    def agent_phase_budget(
        self,
        phase_key: str,
        budget_profile: str = "standard",
    ) -> AgentExecutionBudget:
        """Return a bounded execution budget for a research phase."""
        configured = {
            "clarify_and_brief": AgentExecutionBudget(
                self.agent_phase_clarify_recursion_limit,
                self.agent_phase_clarify_timeout_seconds,
            ),
            "supervisor_research": AgentExecutionBudget(
                self.agent_phase_research_recursion_limit,
                self.agent_phase_research_timeout_seconds,
            ),
            "evidence_compression": AgentExecutionBudget(
                self.agent_phase_compression_recursion_limit,
                self.agent_phase_compression_timeout_seconds,
            ),
            "final_report": AgentExecutionBudget(
                self.agent_phase_final_report_recursion_limit,
                self.agent_phase_final_report_timeout_seconds,
            ),
        }
        budget = configured.get(
            phase_key,
            AgentExecutionBudget(self.agent_recursion_limit, self.agent_max_runtime_seconds),
        )

        recursion_multiplier = 1.0
        timeout_multiplier = 1.0
        if budget_profile == "quick":
            recursion_multiplier = 0.75
            timeout_multiplier = 0.75
        elif budget_profile == "deep_report":
            if phase_key == "supervisor_research":
                recursion_multiplier = 1.5
                timeout_multiplier = 1.5
            elif phase_key == "evidence_compression":
                recursion_multiplier = 1.2
                timeout_multiplier = 1.2
            elif phase_key == "final_report":
                recursion_multiplier = 1.3
                timeout_multiplier = 1.3

        return AgentExecutionBudget(
            recursion_limit=max(
                1,
                min(
                    self.agent_hard_max_recursion_limit,
                    int(round(budget.recursion_limit * recursion_multiplier)),
                ),
            ),
            timeout_seconds=max(
                0.0,
                min(
                    self.agent_hard_max_runtime_seconds,
                    budget.timeout_seconds * timeout_multiplier,
                ),
            ),
        )

    def research_budget_limits(self, budget_profile: str):
        """Return run-level time and work limits for a research profile."""
        from app.agent.runtime import ResearchBudgetLimits

        profiles = {
            "quick": ResearchBudgetLimits("quick", self.agent_quick_slo_seconds, 3, 4, 1, 6, 15),
            "standard": ResearchBudgetLimits(
                "standard", self.agent_standard_slo_seconds, 8, 8, 1, 10, 45
            ),
            "deep_report": ResearchBudgetLimits(
                "deep_report", self.agent_deep_slo_seconds, 12, 12, 2, 12, 75
            ),
            "thorough": ResearchBudgetLimits(
                "thorough", self.agent_thorough_slo_seconds, 30, 24, 3, 20, 180
            ),
        }
        limits = profiles.get(budget_profile, profiles["standard"])
        if self.agent_hard_max_runtime_seconds < limits.total_seconds:
            return ResearchBudgetLimits(
                **{
                    **limits.__dict__,
                    "total_seconds": self.agent_hard_max_runtime_seconds,
                    "writer_reserved_seconds": min(
                        limits.writer_reserved_seconds,
                        self.agent_hard_max_runtime_seconds * 0.25,
                    ),
                }
            )
        return limits


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
        agent_recursion_limit=int(os.getenv("AGENT_RECURSION_LIMIT", "30")),
        agent_max_runtime_seconds=float(os.getenv("AGENT_MAX_RUNTIME_SECONDS", "300")),
        agent_hard_max_recursion_limit=int(os.getenv("AGENT_HARD_MAX_RECURSION_LIMIT", "160")),
        agent_hard_max_runtime_seconds=float(os.getenv("AGENT_HARD_MAX_RUNTIME_SECONDS", "1800")),
        agent_quick_slo_seconds=float(os.getenv("AGENT_QUICK_SLO_SECONDS", "60")),
        agent_standard_slo_seconds=float(os.getenv("AGENT_STANDARD_SLO_SECONDS", "180")),
        agent_deep_slo_seconds=float(os.getenv("AGENT_DEEP_SLO_SECONDS", "300")),
        agent_thorough_slo_seconds=float(os.getenv("AGENT_THOROUGH_SLO_SECONDS", "900")),
        agent_phase_clarify_recursion_limit=int(
            os.getenv("AGENT_PHASE_CLARIFY_RECURSION_LIMIT", "20")
        ),
        agent_phase_clarify_timeout_seconds=float(
            os.getenv("AGENT_PHASE_CLARIFY_TIMEOUT_SECONDS", "120")
        ),
        agent_phase_research_recursion_limit=int(
            os.getenv("AGENT_PHASE_RESEARCH_RECURSION_LIMIT", "90")
        ),
        agent_phase_research_timeout_seconds=float(
            os.getenv("AGENT_PHASE_RESEARCH_TIMEOUT_SECONDS", "900")
        ),
        agent_phase_compression_recursion_limit=int(
            os.getenv("AGENT_PHASE_COMPRESSION_RECURSION_LIMIT", "40")
        ),
        agent_phase_compression_timeout_seconds=float(
            os.getenv("AGENT_PHASE_COMPRESSION_TIMEOUT_SECONDS", "240")
        ),
        agent_phase_final_report_recursion_limit=int(
            os.getenv("AGENT_PHASE_FINAL_REPORT_RECURSION_LIMIT", "60")
        ),
        agent_phase_final_report_timeout_seconds=float(
            os.getenv("AGENT_PHASE_FINAL_REPORT_TIMEOUT_SECONDS", "420")
        ),
        tool_timeout_seconds=float(os.getenv("TOOL_TIMEOUT_SECONDS", "60")),
        db_timeout_seconds=int(os.getenv("DB_TIMEOUT_SECONDS", "20")),
        db_table_preview_rows=int(os.getenv("DB_TABLE_PREVIEW_ROWS", "30")),
        db_query_preview_rows=int(os.getenv("DB_QUERY_PREVIEW_ROWS", "80")),
        db_max_result_chars=int(os.getenv("DB_MAX_RESULT_CHARS", "12000")),
        rag_answer_max_hits=int(os.getenv("RAG_ANSWER_MAX_HITS", "6")),
        rag_answer_max_context_chars=int(os.getenv("RAG_ANSWER_MAX_CONTEXT_CHARS", "10000")),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "dev-only-change-me"),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        allow_register=os.getenv("ALLOW_REGISTER", "true").strip().lower()
        not in {"0", "false", "no"},
    )

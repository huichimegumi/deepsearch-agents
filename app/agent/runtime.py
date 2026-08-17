"""Run-level research budgets and structured execution traces."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class ResearchBudgetLimits:
    """Configured limits for one complete research run."""

    profile: str
    total_seconds: float
    max_search_queries: int
    max_fetched_pages: int
    max_research_rounds: int
    max_llm_calls: int
    writer_reserved_seconds: float
    verifier_reserved_seconds: float = 0.0


@dataclass
class ResearchBudget:
    """Mutable usage ledger for a run with deterministic admission checks."""

    limits: ResearchBudgetLimits
    started_at: float = field(default_factory=monotonic)
    search_queries_used: int = 0
    fetched_pages_used: int = 0
    research_rounds_used: int = 0
    llm_calls_used: int = 0

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.limits.total_seconds - (monotonic() - self.started_at))

    @property
    def deadline_at(self) -> str:
        deadline = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=self.remaining_seconds)
        return deadline.isoformat()

    def phase_timeout(self, phase_key: str, configured_timeout: float) -> float:
        """Return a bounded phase timeout while preserving finalization capacity."""
        shares = {
            "clarify_and_brief": 0.10,
            "supervisor_research": 0.50,
            "evidence_compression": 0.15,
            "final_report": 0.25,
        }
        allocation = self.limits.total_seconds * shares.get(phase_key, 0.25)
        available = self.remaining_seconds
        if phase_key != "final_report":
            available -= self.limits.writer_reserved_seconds
            available -= self.limits.verifier_reserved_seconds
        return max(0.0, min(configured_timeout, allocation, available))

    def take_search_queries(self, requested: int) -> int:
        remaining = max(0, self.limits.max_search_queries - self.search_queries_used)
        accepted = min(max(0, requested), remaining)
        self.search_queries_used += accepted
        return accepted

    def take_fetched_pages(self, requested: int) -> int:
        remaining = max(0, self.limits.max_fetched_pages - self.fetched_pages_used)
        accepted = min(max(0, requested), remaining)
        self.fetched_pages_used += accepted
        return accepted

    def take_research_round(self) -> bool:
        if self.research_rounds_used >= self.limits.max_research_rounds:
            return False
        self.research_rounds_used += 1
        return True

    def take_llm_call(self, phase_key: str) -> bool:
        # M0.1 uses one direct compression call and one direct writer call after research.
        reserve_by_phase = {
            "clarify_and_brief": 2,
            "supervisor_research": 2,
            "evidence_compression": 1,
            "final_report": 0,
        }
        reserve = min(reserve_by_phase.get(phase_key, 0), self.limits.max_llm_calls)
        if self.llm_calls_used >= max(0, self.limits.max_llm_calls - reserve):
            return False
        self.llm_calls_used += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": asdict(self.limits),
            "usage": {
                "search_queries": self.search_queries_used,
                "fetched_pages": self.fetched_pages_used,
                "research_rounds": self.research_rounds_used,
                "llm_calls": self.llm_calls_used,
            },
            "remaining_seconds": round(self.remaining_seconds, 3),
            "deadline_at": self.deadline_at,
        }


def _usage_metadata(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not usage:
        response_metadata = getattr(message, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
    return int(input_tokens), int(output_tokens)


@dataclass
class ResearchRunTrace:
    """Serializable trace summary used by debugging, evals, and baseline reports."""

    run_id: str
    thread_id: str
    budget_profile: str
    budget: ResearchBudget
    started_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    _started_monotonic: float = field(default_factory=monotonic, repr=False)
    status: str = "running"
    degraded: bool = False
    failure_reason: str | None = None
    failure_reasons: list[str] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    tool_calls_by_name: Counter[str] = field(default_factory=Counter)
    subagent_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    search_queries: list[str] = field(default_factory=list)
    search_candidates: int = 0
    fetched_pages: int = 0
    _seen_queries: set[str] = field(default_factory=set, repr=False)
    _seen_sources: set[str] = field(default_factory=set, repr=False)
    _fetched_sources: set[str] = field(default_factory=set, repr=False)
    duplicate_queries: int = 0
    duplicate_sources: int = 0
    queries_with_zero_new_sources: int = 0

    def start_phase(self, phase_key: str, title: str) -> None:
        self.phases.append(
            {
                "phase_key": phase_key,
                "title": title,
                "status": "running",
                "started_at": dt.datetime.now(dt.UTC).isoformat(),
                "_started_monotonic": monotonic(),
                "llm_calls": 0,
                "tool_calls": 0,
                "tool_calls_by_name": {},
                "artifact_status": "missing",
            }
        )

    def finish_phase(
        self,
        phase_key: str,
        status: str,
        reason: str | None = None,
        artifact_status: str | None = None,
    ) -> None:
        phase = next(
            (item for item in reversed(self.phases) if item["phase_key"] == phase_key),
            None,
        )
        if phase is None:
            return
        phase["status"] = status
        phase["elapsed_ms"] = round((monotonic() - phase.pop("_started_monotonic")) * 1000)
        if reason:
            phase["reason"] = reason
            self.record_failure(reason)
        if artifact_status:
            phase["artifact_status"] = artifact_status
        if status not in {"end", "completed"}:
            self.degraded = True

    def mark_phase_artifact(self, phase_key: str, artifact_status: str) -> None:
        phase = next(
            (item for item in reversed(self.phases) if item["phase_key"] == phase_key),
            None,
        )
        if phase:
            phase["artifact_status"] = artifact_status

    def record_failure(self, reason: str | None) -> None:
        if reason and reason not in self.failure_reasons:
            self.failure_reasons.append(reason)

    def record_llm_call(self, phase_key: str, message: Any) -> None:
        self.llm_calls += 1
        input_tokens, output_tokens = _usage_metadata(message)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        phase = next(
            (item for item in reversed(self.phases) if item["phase_key"] == phase_key),
            None,
        )
        if phase:
            phase["llm_calls"] += 1

    def record_tool_call(self, phase_key: str, tool_name: str) -> None:
        self.tool_calls += 1
        self.tool_calls_by_name[tool_name] += 1
        if tool_name == "task":
            self.subagent_calls += 1
        phase = next(
            (item for item in reversed(self.phases) if item["phase_key"] == phase_key),
            None,
        )
        if phase:
            phase["tool_calls"] += 1
            phase_tools = phase["tool_calls_by_name"]
            phase_tools[tool_name] = phase_tools.get(tool_name, 0) + 1

    def record_search(self, queries: list[str], results: list[dict[str, Any]]) -> None:
        new_sources_by_query = {query: 0 for query in queries}
        for query in queries:
            normalized = " ".join(query.casefold().split())
            if normalized in self._seen_queries:
                self.duplicate_queries += 1
            else:
                self._seen_queries.add(normalized)
            self.search_queries.append(query)

        for result in results:
            url = str(result.get("url") or "")
            is_new = bool(url and url not in self._seen_sources)
            if url:
                if is_new:
                    self._seen_sources.add(url)
                else:
                    self.duplicate_sources += 1
            if result.get("raw_content") and url:
                self._fetched_sources.add(url)
            for query in result.get("matched_queries") or []:
                if query in new_sources_by_query and is_new:
                    new_sources_by_query[query] += 1

        self.search_candidates = len(self._seen_sources)
        self.fetched_pages = len(self._fetched_sources)
        self.queries_with_zero_new_sources += sum(
            1 for count in new_sources_by_query.values() if count == 0
        )

    def finalize(
        self,
        *,
        status: str,
        final_result: str | None,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        self.status = "degraded" if self.degraded and status == "completed" else status
        self.record_failure(failure_reason)
        self.failure_reason = self.failure_reasons[0] if self.failure_reasons else None
        result_urls = set(re.findall(r"https?://[^\s)>\]]+", final_result or ""))
        unused_fetched = self._fetched_sources - result_urls
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "thread_id": self.thread_id,
            "started_at": self.started_at,
            "finished_at": dt.datetime.now(dt.UTC).isoformat(),
            "elapsed_ms": round((monotonic() - self._started_monotonic) * 1000),
            "status": self.status,
            "degraded": self.degraded,
            "failure_reason": self.failure_reason,
            "failure_reasons": self.failure_reasons,
            "budget_profile": self.budget_profile,
            "budget": self.budget.snapshot(),
            "phases": self.phases,
            "metrics": {
                "llm_calls": self.llm_calls,
                "tool_calls": self.tool_calls,
                "tool_calls_by_name": dict(self.tool_calls_by_name),
                "subagent_calls": self.subagent_calls,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "search_queries": len(self.search_queries),
                "search_candidates": self.search_candidates,
                "fetched_pages": self.fetched_pages,
            },
            "waste": {
                "duplicate_queries": self.duplicate_queries,
                "duplicate_sources": self.duplicate_sources,
                "queries_with_zero_new_sources": self.queries_with_zero_new_sources,
                "fetched_but_unused_sources": len(unused_fetched),
                "evidence_never_used_in_claims": None,
                "note": "Evidence-level waste becomes available after the M2 evidence schema.",
            },
        }

    @staticmethod
    def write(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_budget_ctx: ContextVar[ResearchBudget | None] = ContextVar("research_budget", default=None)
_trace_ctx: ContextVar[ResearchRunTrace | None] = ContextVar("research_trace", default=None)


def set_research_runtime(
    budget: ResearchBudget, trace: ResearchRunTrace
) -> tuple[Token[ResearchBudget | None], Token[ResearchRunTrace | None]]:
    return _budget_ctx.set(budget), _trace_ctx.set(trace)


def reset_research_runtime(
    tokens: tuple[Token[ResearchBudget | None], Token[ResearchRunTrace | None]],
) -> None:
    budget_token, trace_token = tokens
    _budget_ctx.reset(budget_token)
    _trace_ctx.reset(trace_token)


def get_research_budget() -> ResearchBudget | None:
    return _budget_ctx.get()


def get_research_trace() -> ResearchRunTrace | None:
    return _trace_ctx.get()

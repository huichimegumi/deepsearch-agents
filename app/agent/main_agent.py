"""
主智能体组装与异步执行模块

负责把模型、主提示词、统一证据工具、文件工具和网络研究子智能体组装成 DeepAgent，
并提供 run_deep_agent 作为后续 API 层调用的统一入口。运行时还会为每个
session_id 创建独立工作目录，并把工具调用、子智能体调用和最终结果推送给前端。
"""

import asyncio
import json
import os
import re
import shutil
import uuid
from functools import lru_cache, partial
from pathlib import Path
from typing import Any, Callable

from deepagents import create_deep_agent
from langchain.agents import create_agent
from pydantic import BaseModel, Field

from app.agent.llm import get_model
from app.agent.prompts import main_agent_content
from app.agent.research_workflow import (
    RESEARCH_PHASES,
    SQL_EVIDENCE_CORRECTION_PHASE,
    ResearchPhase,
    build_degraded_phase_output,
    build_phase_prompt,
)
from app.agent.runtime import (
    ResearchBudget,
    ResearchBudgetLimits,
    ResearchRunTrace,
    reset_research_runtime,
    set_research_runtime,
)
from app.agent.subagents.network_search_agent import (
    NETWORK_SEARCH_SUBAGENT_NAME,
    network_search_agent,
)
from app.api.audit import write_audit_event
from app.api.context import (
    reset_research_phase_context,
    reset_session_context,
    set_research_phase_context,
    set_session_context,
    set_thread_context,
    set_user_context,
)
from app.api.monitor import monitor
from app.config import AgentExecutionBudget, get_settings
from app.memory.checkpoint import get_short_term_checkpointer
from app.memory.service import format_memories_for_prompt, search_memories
from app.research.claims import (
    ClaimDraft,
    ClaimValidationReport,
    ReportCitationValidation,
    validate_claims,
    validate_report_citations,
)
from app.research.local_retrieval import local_evidence_boundary, require_local_retrieval
from app.research.local_scope import enforce_local_absence_scope
from app.research.source_provenance import document_catalog, enforce_local_source_references
from app.research.source_scope import requires_local_only
from app.tools.evidence_tool import collect_evidence
from app.tools.local_research_tool import collect_local_evidence
from app.tools.markdown_tools import write_markdown_artifact
from app.tools.memory_tools import remember_user_memory, search_user_memory
from app.tools.pdf_tools import convert_md_to_pdf
from app.tools.tavily_tool import research_search
from app.tools.upload_file_read_tool import read_file_content


@lru_cache(maxsize=1)
def get_planner_agent():
    """Return the direct model used by single-call planning phases."""
    return get_model()


@lru_cache(maxsize=1)
def get_research_agent():
    """Build the only phase agent that can call researcher subagents."""
    return create_deep_agent(
        model=get_model(),
        system_prompt=main_agent_content["system_prompt"],
        tools=list(_research_tools()),
        checkpointer=get_short_term_checkpointer(),
        subagents=[network_search_agent],
    )


@lru_cache(maxsize=1)
def get_indexed_local_research_agent():
    """No DeepAgents filesystem, planning, memory, or delegation middleware."""
    return create_agent(
        model=get_model(),
        tools=[collect_local_evidence],
        system_prompt=(
            "You research already indexed local documents only. Your sole tool is collect_evidence, "
            "whose source is fixed to local documents by the backend. Use the prefetched Evidence "
            "when sufficient; otherwise make focused local queries within the remaining budget. "
            "At most two supplemental tool requests are admitted for this phase. "
            "Earlier briefs may name unavailable tools: do not call them. Do not list/read/write "
            "files, maintain todos, manage memory, delegate tasks, search the web, or query SQL. "
            "Return an Evidence ledger and limitations, not a file or final report. Never infer "
            "full-document or corpus absence from bounded retrieval."
        ),
        checkpointer=get_short_term_checkpointer(),
    )


def _research_tools():
    """Return the bounded direct tools available during the research phase."""
    return (
        collect_evidence,
        read_file_content,
        remember_user_memory,
        search_user_memory,
    )


@lru_cache(maxsize=1)
def get_writer_agent():
    """Return the direct model used for one-call report synthesis."""
    return get_model()


def get_main_agent():
    """Backward-compatible accessor for the research-capable agent."""
    return get_research_agent()


# 当前文件位于 app/agent/main_agent.py，parents[1] 即 app 目录
project_root_path = Path(__file__).parents[1].resolve()


class PhaseBudgetExceeded(RuntimeError):
    """Raised when an in-process phase guard decides the phase must stop."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class EntityResolutionRejected(RuntimeError):
    """Stop SQL correction when a multi-clue entity cannot be grounded."""


class ResearchBrief(BaseModel):
    """Bounded, machine-readable output for the clarification phase."""

    research_question: str
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    source_plan: list[str] = Field(default_factory=list)
    subquestions: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        sections = [
            ("Research question", [self.research_question]),
            ("Constraints", self.constraints),
            ("Working assumptions", self.assumptions),
            ("Source plan", self.source_plan),
            ("Research subquestions", self.subquestions),
        ]
        return "# Research Brief\n\n" + "\n\n".join(
            f"## {title}\n" + "\n".join(f"- {item}" for item in items if item)
            for title, items in sections
        )


class CompressedEvidence(BaseModel):
    """Bounded, machine-readable output for the compression phase."""

    claims: list[ClaimDraft] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    report_outline: list[str] = Field(default_factory=list)

    def to_markdown(self, validation: ClaimValidationReport | None = None) -> str:
        if validation is None:
            validation = validate_claims(self.claims, available_evidence_ids=())

        accepted = []
        for claim in validation.accepted:
            evidence = " ".join(f"[{item}]" for item in claim.evidence_ids)
            limitations = (
                "\n  - Limitations: " + "; ".join(claim.limitations) if claim.limitations else ""
            )
            accepted.append(
                f"- [{claim.claim_id}] ({claim.kind.value}) {claim.text}\n"
                f"  - Evidence: {evidence}{limitations}"
            )

        rejected = []
        for item in validation.rejected:
            reasons = "; ".join(f"{issue.code.value}: {issue.detail}" for issue in item.issues)
            rejected.append(f"- {item.draft.text}\n  - Rejected: {reasons}")

        sections = [
            ("Validated claims", accepted),
            ("Rejected claim drafts", rejected),
            ("Conflicts", [f"- {item}" for item in self.conflicts if item]),
            (
                "Uncertainties and boundaries",
                [f"- {item}" for item in self.uncertainties if item],
            ),
            (
                "Recommended report outline",
                [f"- {item}" for item in self.report_outline if item],
            ),
        ]
        return "# Validated Claim Package\n\n" + "\n\n".join(
            f"## {title}\n" + ("\n".join(items) or "- None recorded") for title, items in sections
        )


class SQLCorrectionProposal(BaseModel):
    """One read-only analytical query proposed for deterministic backend execution."""

    query: str = Field(
        min_length=1,
        description="One complete read-only analytical SQL SELECT or WITH query.",
    )


class EntityClueAssessment(BaseModel):
    """One clue-to-candidate link backed by fetched Web Evidence."""

    clue: str = Field(min_length=1)
    candidate: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    supported: bool = False


class EntityResolutionProposal(BaseModel):
    """A cross-clue entity plus the physical database field that should contain it."""

    resolved_entity: str = ""
    all_clues_supported: bool = False
    clues: list[EntityClueAssessment] = Field(default_factory=list)
    table_name: str = ""
    column_name: str = ""
    recovery_queries: list[str] = Field(default_factory=list, max_length=2)


SQL_CORRECTION_MAX_PROPOSALS = 2
ENTITY_RECOVERY_MAX_ROUNDS = 3
ENTITY_RESOLUTION_MAX_ATTEMPTS = ENTITY_RECOVERY_MAX_ROUNDS + 1
ENTITY_RECOVERY_MAX_QUERIES_PER_ROUND = 2
ENTITY_RECOVERY_MAX_PAGES_PER_ROUND = 2
SQL_FENCE_PATTERN = re.compile(r"```sql\s*.*?```", re.IGNORECASE | re.DOTALL)


def _requires_multiclue_entity_resolution(task_query: str) -> bool:
    return bool(re.search(r"\bclues?\b|线索", task_query, flags=re.IGNORECASE))


def _create_research_budget(
    task_query: str,
    limits: ResearchBudgetLimits,
    *,
    sql_entity_recovery_enabled: bool,
) -> ResearchBudget:
    budget = ResearchBudget(limits)
    if sql_entity_recovery_enabled and _requires_multiclue_entity_resolution(task_query):
        budget.reserve_search_queries(2)
        budget.reserve_fetched_pages(2)
    return budget


def _entity_resolution_rejection_reason(
    proposal: object,
    *,
    parsing_error: object,
    web_evidence_ids: frozenset[str],
    semantic_catalog: dict[str, tuple[str, ...]],
) -> str | None:
    """Classify a proposal without exposing clue, candidate, or Evidence content."""
    if parsing_error or not isinstance(proposal, EntityResolutionProposal):
        return "output_invalid"
    if not proposal.all_clues_supported or any(not item.supported for item in proposal.clues):
        return "clues_unsupported"
    normalized_entity = proposal.resolved_entity.strip().casefold()
    if not normalized_entity:
        return "entity_missing"
    if len(proposal.clues) < 2:
        return "clues_insufficient"
    if any(not item.candidate.strip() for item in proposal.clues):
        return "candidate_missing"
    if any(item.candidate.strip().casefold() != normalized_entity for item in proposal.clues):
        return "candidate_conflict"
    if any(not item.evidence_ids for item in proposal.clues):
        return "web_evidence_missing"
    if any(
        evidence_id not in web_evidence_ids
        for item in proposal.clues
        for evidence_id in item.evidence_ids
    ):
        return "web_evidence_unknown"
    if proposal.table_name not in semantic_catalog:
        return "table_unknown"
    if proposal.column_name not in semantic_catalog.get(proposal.table_name, ()):
        return "column_unknown"
    return None


async def _ground_multiclue_entity(
    *,
    model,
    task_query: str,
    phase_key: str,
    phase_deadline: float,
    research_budget: ResearchBudget,
    run_trace: ResearchRunTrace,
) -> bool:
    """Resolve all task clues to one Web-backed entity and one unique database value."""
    catalog = run_trace.semantic_table_columns
    if not catalog:
        run_trace.record_sql_entity_resolution(resolved=False, value_matched=False)
        run_trace.record_failure("sql_entity_resolution_context_missing")
        return False
    loop = asyncio.get_running_loop()
    proposal = None
    for resolution_index in range(ENTITY_RESOLUTION_MAX_ATTEMPTS):
        web_ledger = run_trace.render_evidence_ledger(
            max_records=24,
            max_total_content_chars=20_000,
            max_record_content_chars=4_000,
            evidence_kinds=("web_page",),
        )
        if not web_ledger:
            web_ledger = (
                "No fetched Web Evidence is available. Set all_clues_supported=false and provide "
                "specific recovery_queries for the unsupported clues; do not infer an entity."
            )
        if not research_budget.take_llm_call(phase_key):
            raise PhaseBudgetExceeded("llm_call_limit")
        remaining_seconds = phase_deadline - loop.time()
        if remaining_seconds <= 0:
            raise TimeoutError
        prompt = "\n\n".join(
            (
                f"【Original task】\n{task_query}",
                "【Fetched Web Evidence】\n" + web_ledger,
                "【Allowed database entity fields】\n"
                + json.dumps(catalog, ensure_ascii=False, sort_keys=True),
                (
                    "Resolve the single place/entity jointly supported by every clue. A country or "
                    "place mentioned by only one clue is not the answer. Bind every clue to one or "
                    "more fetched ev1_web evidence IDs. Set all_clues_supported=false if any clue is "
                    "unverified or contradictory. When support is incomplete, provide at most two "
                    "specific recovery_queries for the unsupported clues; preserve their most "
                    "discriminating names or literal phrases and do not request generic background. "
                    "Select table_name and column_name exactly from the allowed catalog; do not "
                    "invent a database value or namespace prefix."
                ),
            )
        )
        structured_model = model.with_structured_output(
            EntityResolutionProposal,
            include_raw=True,
        )
        response = await asyncio.wait_for(
            structured_model.ainvoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a conservative multi-clue entity resolver. Return only the "
                            "required structured object and never guess an unsupported intersection."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
            ),
            timeout=remaining_seconds,
        )
        raw = response.get("raw") if isinstance(response, dict) else None
        proposal = response.get("parsed") if isinstance(response, dict) else response
        parsing_error = response.get("parsing_error") if isinstance(response, dict) else None
        run_trace.record_llm_call(phase_key, raw)
        rejection_reason = _entity_resolution_rejection_reason(
            proposal,
            parsing_error=parsing_error,
            web_evidence_ids=run_trace.web_evidence_ids,
            semantic_catalog=catalog,
        )
        if rejection_reason is None:
            break
        run_trace.record_sql_entity_resolution(resolved=False, value_matched=False)
        recovery_queries = []
        if isinstance(proposal, EntityResolutionProposal):
            recovery_queries = list(
                dict.fromkeys(query.strip() for query in proposal.recovery_queries if query.strip())
            )
        if resolution_index == 0:
            recovery_allowance = research_budget.release_search_query_reserve()
            recovery_page_allowance = research_budget.release_fetched_page_reserve()
        else:
            recovery_allowance = min(
                ENTITY_RECOVERY_MAX_QUERIES_PER_ROUND,
                research_budget.available_search_queries,
            )
            recovery_page_allowance = min(
                ENTITY_RECOVERY_MAX_PAGES_PER_ROUND,
                research_budget.available_fetched_pages,
            )
        if (
            resolution_index < ENTITY_RESOLUTION_MAX_ATTEMPTS - 1
            and rejection_reason == "clues_unsupported"
            and recovery_queries
            and recovery_allowance > 0
            and recovery_page_allowance > 0
        ):
            previous_web_ids = run_trace.web_evidence_ids
            run_trace.record_tool_call(phase_key, research_search.name)
            remaining_seconds = phase_deadline - loop.time()
            if remaining_seconds <= 0:
                raise TimeoutError
            await asyncio.wait_for(
                research_search.ainvoke(
                    {
                        "queries": recovery_queries[:recovery_allowance],
                        "backend": "auto",
                        "topic": "general",
                        "max_results": min(6, recovery_page_allowance * 3),
                        "fetch_full_page": True,
                        "max_fetched_pages": recovery_page_allowance,
                    }
                ),
                timeout=remaining_seconds,
            )
            if run_trace.web_evidence_ids != previous_web_ids:
                continue
        run_trace.record_failure(f"sql_entity_resolution_{rejection_reason}")
        return False
    else:  # pragma: no cover - the bounded loop always breaks or returns
        return False

    assert isinstance(proposal, EntityResolutionProposal)
    run_trace.record_tool_call(phase_key, collect_evidence.name)
    remaining_seconds = phase_deadline - loop.time()
    if remaining_seconds <= 0:
        raise TimeoutError
    tool_result = await asyncio.wait_for(
        collect_evidence.ainvoke(
            {
                "source": "sql",
                "operation": "match_column_value",
                "query": proposal.resolved_entity,
                "table_name": proposal.table_name,
                "column_name": proposal.column_name,
            }
        ),
        timeout=remaining_seconds,
    )
    try:
        payload = json.loads(tool_result)
        value_matched = payload.get("status") == "OK" and len(payload.get("records", ())) == 1
    except (TypeError, ValueError, AttributeError):
        value_matched = False
    run_trace.record_sql_entity_resolution(resolved=True, value_matched=value_matched)
    if not value_matched:
        run_trace.record_failure("sql_entity_value_not_unique")
    return value_matched


def _render_validated_compression(
    parsed: CompressedEvidence,
    run_trace: ResearchRunTrace,
) -> str:
    validation = validate_claims(
        parsed.claims,
        available_evidence_ids=run_trace.claim_eligible_evidence_ids,
    )
    run_trace.record_claim_validation(validation, drafts=parsed.claims)
    # Unchecked outlines, rejected drafts and free-text gaps must not become Writer facts.
    return run_trace.render_accepted_claim_package()


def _attach_required_executed_sql(
    report_markdown: str,
    run_trace: ResearchRunTrace,
) -> str:
    """Attach exactly one executed analytical query when the caller requires SQL output."""
    if os.getenv("INCLUDE_EXECUTED_SQL_IN_REPORT", "").strip() != "1":
        return report_markdown
    query = run_trace.preferred_analytical_sql_query
    if not query:
        return report_markdown
    report_without_sql_fences = SQL_FENCE_PATTERN.sub("", report_markdown).rstrip()
    run_trace.report_sql_query_attached = True
    return (
        f"{report_without_sql_fences}\n\n## Executed analytical SQL\n\n```sql\n{query.strip()}\n```"
    )


def _local_report_boundary(report: str, run_trace: ResearchRunTrace, *, candidate_kind: str):
    return enforce_local_source_references(
        report, run_trace, candidate_kind=candidate_kind
    ) or enforce_local_absence_scope(report, run_trace, candidate_kind=candidate_kind)


def _enforce_final_report_citations(
    *,
    report_markdown: str,
    compressed_fallback: str,
    run_trace: ResearchRunTrace,
) -> tuple[str, ReportCitationValidation]:
    source_boundary = _local_report_boundary(
        report_markdown, run_trace, candidate_kind="final_candidate"
    )
    if source_boundary is not None:
        # This is a backend status notice, not a factual answer requiring Claim citations.
        validation = validate_report_citations(
            source_boundary, allowed_evidence_ids=(), citations_required=False
        )
        run_trace.record_report_citation_validation(validation)
        return source_boundary, validation
    validation = validate_report_citations(
        report_markdown,
        allowed_evidence_ids=run_trace.claim_evidence_ids,
        citations_required=bool(run_trace.claim_eligible_evidence_ids or run_trace.rejected_claims),
    )
    if validation.valid:
        run_trace.record_report_citation_validation(validation)
        return report_markdown, validation

    reasons: list[str] = []
    if validation.unknown_evidence_ids:
        reasons.append("the writer referenced one or more unknown evidence IDs")
    if validation.missing_required_citations:
        reasons.append("the writer omitted all validated evidence citations")
    reason = "; ".join(reasons)
    run_trace.degraded = True
    run_trace.record_failure("final_report_citation_validation_failed")
    # Never trust caller-supplied compression Markdown as a validated fallback.
    # Keep the argument for existing callers; delivery comes from the typed registry.
    fallback = run_trace.render_accepted_claim_package()
    fallback_report = (
        "# Evidence-Validated Partial Result\n\n"
        f"> The generated report failed citation validation ({reason}). "
        "The backend returned structurally accepted Claims; factual support is not verified.\n\n"
        f"{fallback}"
    )
    source_boundary = _local_report_boundary(
        fallback_report, run_trace, candidate_kind="citation_fallback"
    )
    if source_boundary is not None:
        fallback_validation = validate_report_citations(
            source_boundary, allowed_evidence_ids=(), citations_required=False
        )
        run_trace.record_report_citation_validation(fallback_validation)
        return source_boundary, fallback_validation
    fallback_validation = validate_report_citations(
        fallback_report,
        allowed_evidence_ids=run_trace.claim_evidence_ids,
        citations_required=bool(run_trace.claim_eligible_evidence_ids or run_trace.rejected_claims),
    )
    if fallback_validation.valid and run_trace.claim_ids:
        run_trace.report_used_claim_fallback = True
        run_trace.record_report_citation_validation(fallback_validation)
        return fallback_report, fallback_validation

    run_trace.report_citation_withheld = True
    run_trace.record_failure("claim_fallback_citation_validation_failed")
    notice = (
        "# Report delivery withheld\n\n"
        "The generated report failed evidence citation validation, and no usable "
        "Claim fallback passed the delivery checks. No research answer is delivered."
    )
    notice_validation = validate_report_citations(
        notice, allowed_evidence_ids=(), citations_required=False
    )
    run_trace.record_report_citation_validation(notice_validation)
    return notice, notice_validation


def _enforce_required_source_delivery(
    report: str,
    validation: ReportCitationValidation,
    run_trace: ResearchRunTrace,
    required_sources: tuple[str, ...],
) -> tuple[str, ReportCitationValidation]:
    """Withhold an answer when caller-required source types were not cited."""
    eligible = set(run_trace.claim_eligible_evidence_ids)

    def source_of(eid: str) -> str:
        value = getattr(run_trace._evidence_records_by_id[eid], "source", "")
        return str(getattr(value, "value", value))

    collected = {source_of(eid) for eid in eligible}
    cited = {source_of(eid) for eid in validation.cited_evidence_ids if eid in eligible}
    if set(required_sources) <= collected and set(required_sources) <= cited:
        return report, validation
    run_trace.degraded = True
    run_trace.report_citation_withheld = True
    run_trace.report_used_claim_fallback = False
    run_trace.record_failure("required_evidence_source_missing")
    notice = (
        "# Report delivery withheld\n\n"
        "The requested source types were not all collected and cited by eligible "
        "Evidence. The available material is insufficient for this report."
    )
    notice_validation = validate_report_citations(
        notice, allowed_evidence_ids=(), citations_required=False
    )
    run_trace.record_report_citation_validation(notice_validation)
    return notice, notice_validation


def _attach_backend_evidence_ledger(
    phase_result: str | None,
    run_trace: ResearchRunTrace,
) -> str | None:
    ledger = run_trace.render_evidence_ledger()
    if not ledger:
        return phase_result
    if not phase_result:
        return ledger
    return f"{phase_result.rstrip()}\n\n{ledger}"


def _compression_phase_outputs(
    phase_outputs: dict[str, str],
    run_trace: ResearchRunTrace,
) -> dict[str, str]:
    """Build a Claim-safe handoff without replaying discovery-only supervisor citations."""
    claim_ledger = run_trace.render_evidence_ledger(
        claim_eligible_only=True,
        source_priority=("web", "sql"),
    )
    supervisor_handoff = (
        "Only the Evidence IDs below are eligible to support compressed Claims. "
        "Schema, samples, and semantic-formula discovery records were removed by the backend."
    )
    if claim_ledger:
        supervisor_handoff = f"{supervisor_handoff}\n\n{claim_ledger}"
    else:
        supervisor_handoff = (
            f"{supervisor_handoff}\n\nNo claim-eligible Evidence was collected; return evidence "
            "gaps instead of factual Claims."
        )
    return {
        key: value
        for key, value in {
            "clarify_and_brief": phase_outputs.get("clarify_and_brief", ""),
            "supervisor_research": supervisor_handoff,
        }.items()
        if value
    }


async def _prefetch_sql_semantic_context(
    *,
    task_query: str,
    run_trace: ResearchRunTrace,
    timeout_seconds: float,
) -> str:
    """Deterministically load task-relevant pinned formulas before Supervisor research."""
    if (
        not os.getenv("EVIDENCE_SQLITE_PATH", "").strip()
        or not os.getenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", "").strip()
    ):
        return ""
    if timeout_seconds <= 0:
        return ""
    run_trace.record_tool_call("supervisor_research", collect_evidence.name)
    try:
        await asyncio.wait_for(
            collect_evidence.ainvoke(
                {
                    "source": "sql",
                    "operation": "search_semantic_knowledge",
                    "query": task_query,
                }
            ),
            timeout=min(timeout_seconds, 10.0),
        )
    except (TimeoutError, asyncio.TimeoutError):
        return ""
    return run_trace.render_evidence_ledger(
        max_records=8,
        max_total_content_chars=8_000,
        evidence_kinds=("database_semantics",),
    )


def _enforce_research_evidence_requirements(
    phase_result: str | None,
    run_trace: ResearchRunTrace,
) -> str | None:
    if os.getenv("REQUIRE_ANALYTICAL_SQL_EVIDENCE", "").strip() != "1":
        return phase_result
    if run_trace.has_analytical_sql_evidence:
        return phase_result
    run_trace.degraded = True
    run_trace.record_failure("analytical_sql_evidence_missing")
    notice = (
        "# Backend Evidence Requirement\n\n"
        "- Analytical SQL Evidence is missing. Schema descriptions and sample rows are "
        "discovery-only and cannot support final business or benchmark claims.\n"
        "- The final answer must report this evidence gap instead of treating discovery "
        "records as query results."
    )
    if not phase_result:
        return notice
    return f"{phase_result.rstrip()}\n\n{notice}"


def _should_attempt_sql_evidence_correction(run_trace: ResearchRunTrace) -> bool:
    """Gate the SQL-only correction to runs that explicitly require analytical SQL."""
    return (
        os.getenv("REQUIRE_ANALYTICAL_SQL_EVIDENCE", "").strip() == "1"
        and run_trace.can_attempt_sql_correction
        and run_trace.sql_correction_attempts == 0
    )


def _render_sql_correction_ledger(run_trace: ResearchRunTrace) -> str:
    """Prefer compact formula grounding plus claim context over a duplicated full schema."""
    semantic_ledger = run_trace.render_evidence_ledger(
        max_records=16,
        max_total_content_chars=16_000,
        evidence_kinds=("database_semantics", "database_value_match"),
    )
    if not semantic_ledger:
        return run_trace.render_evidence_ledger(
            max_total_content_chars=32_000,
            max_record_content_chars=4_000,
            source_priority=("web", "sql"),
        )
    claim_context = run_trace.render_evidence_ledger(
        max_records=24,
        max_total_content_chars=16_000,
        max_record_content_chars=4_000,
        source_priority=("web", "sql"),
        claim_eligible_only=True,
    )
    parts = [
        "# SQL Correction Formula Context\n"
        "The discovery records include formula dependencies, physical columns/tables, and any "
        "validated database entity values needed to construct the analytical query.",
        semantic_ledger,
    ]
    if claim_context:
        parts.extend(
            (
                "# Claim-Eligible Entity Context\n"
                "Use this context to resolve requested entities and filters.",
                claim_context,
            )
        )
    return "\n\n".join(parts)


async def _run_sql_evidence_correction(
    *,
    model,
    task_query: str,
    research_brief: str,
    budget: AgentExecutionBudget,
    budget_profile: str,
    research_budget: ResearchBudget,
    run_trace: ResearchRunTrace,
) -> bool:
    """Execute one structured SQL proposal plus one bounded result-aware repair."""
    phase = SQL_EVIDENCE_CORRECTION_PHASE
    budget_data = _budget_payload(
        budget=budget,
        budget_profile=budget_profile,
        remaining_workflow_seconds=research_budget.remaining_seconds,
    )
    run_trace.start_phase(phase.key, phase.title)
    monitor.report_research_phase(phase.key, phase.title, "start", budget_data)
    write_audit_event(
        "research_phase_started",
        {"phase_key": phase.key, "phase_title": phase.title, **budget_data},
    )
    phase_status = "end"
    reason = None
    error = None
    success = False
    llm_recorded = False
    repair_started = False
    repair_trigger = ""
    empty_result_repair_started = False
    phase_token = set_research_phase_context(phase.key)
    try:
        loop = asyncio.get_running_loop()
        phase_deadline = loop.time() + budget.timeout_seconds
        if os.getenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", "").strip():
            run_trace.record_tool_call(phase.key, collect_evidence.name)
            remaining_seconds = phase_deadline - loop.time()
            if remaining_seconds <= 0:
                raise TimeoutError
            await asyncio.wait_for(
                collect_evidence.ainvoke(
                    {
                        "source": "sql",
                        "operation": "search_semantic_knowledge",
                        "query": task_query,
                    }
                ),
                timeout=remaining_seconds,
            )
        if _requires_multiclue_entity_resolution(task_query):
            llm_calls_before_entity_resolution = run_trace.llm_calls
            entity_grounded = await _ground_multiclue_entity(
                model=model,
                task_query=task_query,
                phase_key=phase.key,
                phase_deadline=phase_deadline,
                research_budget=research_budget,
                run_trace=run_trace,
            )
            llm_recorded = run_trace.llm_calls > llm_calls_before_entity_resolution
            if not entity_grounded:
                # Context-only rejection does not make a model call and should not create a
                # synthetic LLM usage record in the correction phase.
                llm_recorded = True
                raise EntityResolutionRejected
        prompt = "\n\n".join(
            (
                f"【用户原始问题】\n{task_query}",
                f"【Research Brief】\n{research_brief or 'No completed brief was captured.'}",
                _render_sql_correction_ledger(run_trace),
                phase.instruction,
            )
        )
        structured_model = model.with_structured_output(
            SQLCorrectionProposal,
            include_raw=True,
        )
        previous_query = ""
        validation_feedback = ""
        proposed_queries: set[str] = set()
        for proposal_index in range(SQL_CORRECTION_MAX_PROPOSALS):
            if not research_budget.take_llm_call(phase.key):
                raise PhaseBudgetExceeded("llm_call_limit")
            if proposal_index:
                repair_started = True
                empty_result_repair_started = repair_trigger == "NO_EVIDENCE"
            remaining_seconds = phase_deadline - loop.time()
            if remaining_seconds <= 0:
                raise TimeoutError
            if proposal_index:
                if repair_trigger == "NO_EVIDENCE":
                    system_instruction = (
                        "The previous SQL proposal executed successfully but returned zero rows. "
                        "Return exactly one different read-only analytical SQL query through the "
                        "required structured schema. Preserve the requested entity and computation, "
                        "but relax only filters that are unsupported by the supplied Evidence "
                        "Ledger. Use exact schema identifiers and never fabricate values."
                    )
                    user_prompt = (
                        f"{prompt}\n\n【Empty-result proposal】\n{previous_query}\n\n"
                        "Repair only the over-constrained or unsupported filtering logic."
                    )
                elif repair_trigger == "VALIDATION_ERROR":
                    system_instruction = (
                        "The previous SQL proposal failed the backend's read-only SQLite preflight "
                        "and was not executed. Return exactly one different query through the "
                        "required structured schema. Copy the supplied compiled_sql_expression "
                        "for every derived metric and use only its required_tables and physical "
                        "columns. Never use a metric name or formula alias as a physical column."
                    )
                    user_prompt = (
                        f"{prompt}\n\n【Preflight-rejected proposal】\n{previous_query}\n\n"
                        f"【Preflight error】\n{validation_feedback}\n\n"
                        "Repair the invalid identifiers before execution."
                    )
                else:
                    system_instruction = (
                        "The previous SQL proposal was rejected by the database. Return exactly one "
                        "different read-only analytical SQL query through the required structured "
                        "schema. Re-check every table and column against the supplied Evidence Ledger; "
                        "do not invent a requested metric as a physical column."
                    )
                    user_prompt = (
                        f"{prompt}\n\n【Rejected proposal】\n{previous_query}\n\n"
                        "Repair only the SQL identifier or expression error."
                    )
            else:
                system_instruction = (
                    "You are a SQL correction planner. Return exactly one read-only analytical "
                    "SQL query through the required structured schema. Use only table names and "
                    "columns present in the supplied Evidence Ledger. Derive requested metrics "
                    "with SQL expressions instead of inventing physical columns."
                )
                user_prompt = prompt
            response = await asyncio.wait_for(
                structured_model.ainvoke(
                    [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ]
                ),
                timeout=remaining_seconds,
            )
            raw = response.get("raw") if isinstance(response, dict) else None
            proposal = response.get("parsed") if isinstance(response, dict) else response
            parsing_error = response.get("parsing_error") if isinstance(response, dict) else None
            run_trace.record_llm_call(phase.key, raw)
            llm_recorded = True
            if parsing_error or not isinstance(proposal, SQLCorrectionProposal):
                raise ValueError(f"structured_output_error: {parsing_error!r}")
            normalized_query = " ".join(proposal.query.strip().rstrip(";").split()).casefold()
            if normalized_query in proposed_queries:
                raise ValueError("sql_correction_duplicate_proposal")
            proposed_queries.add(normalized_query)
            previous_query = proposal.query
            if run_trace.has_executable_sql_semantics:
                run_trace.record_tool_call(phase.key, collect_evidence.name)
                remaining_seconds = phase_deadline - loop.time()
                if remaining_seconds <= 0:
                    raise TimeoutError
                validation_result = await asyncio.wait_for(
                    collect_evidence.ainvoke(
                        {
                            "source": "sql",
                            "operation": "validate_query",
                            "query": proposal.query,
                        }
                    ),
                    timeout=remaining_seconds,
                )
                try:
                    validation_payload = json.loads(validation_result)
                    validation_status = str(validation_payload.get("status", ""))
                    validation_feedback = "; ".join(validation_payload.get("warnings", ()))
                except (TypeError, ValueError, AttributeError):
                    validation_status = ""
                    validation_feedback = "The backend returned an unreadable validation result."
                if validation_status != "OK":
                    repair_trigger = "VALIDATION_ERROR"
                    continue
            run_trace.record_tool_call(phase.key, collect_evidence.name)
            remaining_seconds = phase_deadline - loop.time()
            if remaining_seconds <= 0:
                raise TimeoutError
            tool_result = await asyncio.wait_for(
                collect_evidence.ainvoke(
                    {
                        "source": "sql",
                        "operation": "query",
                        "query": proposal.query,
                    }
                ),
                timeout=remaining_seconds,
            )
            success = run_trace.has_analytical_sql_evidence
            if success:
                break
            try:
                tool_status = str(json.loads(tool_result).get("status", ""))
            except (TypeError, ValueError, AttributeError):
                tool_status = ""
            if tool_status not in {"ERROR", "NO_EVIDENCE"}:
                break
            repair_trigger = tool_status
        if not success:
            reason = "sql_correction_no_analytical_evidence"
    except asyncio.CancelledError:
        phase_status = "cancelled"
        reason = "cancelled"
        raise
    except (TimeoutError, asyncio.TimeoutError) as exc:
        phase_status = "budget_exceeded"
        reason = "timeout"
        error = repr(exc)
    except EntityResolutionRejected:
        reason = "sql_correction_entity_unresolved"
    except PhaseBudgetExceeded as exc:
        phase_status = "budget_exceeded"
        reason = exc.reason
        error = repr(exc)
    except ValueError as exc:
        phase_status = "error"
        reason = str(exc).split(":", 1)[0] or "ValueError"
        error = repr(exc)
    except Exception as exc:  # noqa: BLE001 - correction failure degrades to an evidence gap
        phase_status = "error"
        reason = exc.__class__.__name__
        error = repr(exc)
    finally:
        if not llm_recorded:
            run_trace.record_llm_call(phase.key, None)
        reset_research_phase_context(phase_token)
        if repair_started:
            run_trace.record_sql_correction_repair(success=success)
            if empty_result_repair_started:
                run_trace.record_sql_correction_empty_result_repair(success=success)
        run_trace.record_sql_correction(success=success)
        if reason:
            run_trace.record_failure(reason)
        run_trace.finish_phase(
            phase.key,
            phase_status,
            artifact_status="usable" if success else "missing",
        )

    phase_end_data = {"success": success, **budget_data}
    if reason:
        phase_end_data["reason"] = reason
    if error:
        phase_end_data["error"] = error
    monitor.report_research_phase(
        phase.key,
        phase.title,
        phase_status,
        phase_end_data,
    )
    write_audit_event(
        "research_phase_finished",
        {
            "phase_key": phase.key,
            "phase_title": phase.title,
            "status": phase_status,
            **phase_end_data,
        },
    )
    return success


async def _astream_with_runtime_limit(agent, payload, config, timeout_seconds: float):
    if timeout_seconds <= 0:
        raise PhaseBudgetExceeded("phase_time_exhausted")

    async with asyncio.timeout(timeout_seconds):
        async for chunk in agent.astream(payload, config=config):
            yield chunk


def _is_upstream_timeout_exception(exc: BaseException) -> bool:
    """Recognize provider timeout wrappers without importing a provider-specific SDK."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, asyncio.TimeoutError)):
            return True
        if "timeout" in current.__class__.__name__.casefold():
            return True
        current = current.__cause__ or current.__context__
    return False


def _message_text(message) -> str:
    """Normalize provider-specific message content into plain text."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return str(content or "").strip()


async def _run_direct_phase(
    *,
    model,
    phase: ResearchPhase,
    prompt: str,
    budget: AgentExecutionBudget,
    budget_profile: str,
    research_budget: ResearchBudget,
    run_trace: ResearchRunTrace,
    schema: type[BaseModel] | None = None,
    structured_renderer: Callable[[BaseModel], str] | None = None,
    emit_final_result: bool = False,
) -> str | None:
    """Run a phase as exactly one model call with no DeepAgents built-ins."""
    budget_data = _budget_payload(budget=budget, budget_profile=budget_profile)
    run_trace.start_phase(phase.key, phase.title)
    monitor.report_research_phase(phase.key, phase.title, "start", budget_data)
    write_audit_event(
        "research_phase_started",
        {"phase_key": phase.key, "phase_title": phase.title, **budget_data},
    )
    status = "end"
    reason = None
    error = None
    result_text = None
    llm_recorded = False
    llm_attempted = False
    phase_token = set_research_phase_context(phase.key)
    try:
        if budget.timeout_seconds <= 0:
            raise PhaseBudgetExceeded("phase_time_exhausted")
        if not research_budget.take_llm_call(phase.key):
            raise PhaseBudgetExceeded("llm_call_limit")
        llm_attempted = True
        messages = [
            {"role": "system", "content": main_agent_content["system_prompt"]},
            {"role": "user", "content": prompt},
        ]
        if schema:
            structured_model = model.with_structured_output(schema, include_raw=True)
            response = await asyncio.wait_for(
                structured_model.ainvoke(messages), timeout=budget.timeout_seconds
            )
            raw = response.get("raw") if isinstance(response, dict) else None
            parsed = response.get("parsed") if isinstance(response, dict) else response
            parsing_error = response.get("parsing_error") if isinstance(response, dict) else None
            if raw is not None:
                run_trace.record_llm_call(phase.key, raw)
                llm_recorded = True
            if parsing_error or parsed is None:
                raise ValueError(f"structured_output_error: {parsing_error!r}")
            result_text = (
                structured_renderer(parsed)
                if structured_renderer is not None
                else parsed.to_markdown()
            )
        else:
            response = await asyncio.wait_for(
                model.ainvoke(messages), timeout=budget.timeout_seconds
            )
            run_trace.record_llm_call(phase.key, response)
            llm_recorded = True
            result_text = _message_text(response)
            result_text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", result_text).strip()

        if not result_text:
            raise ValueError("empty_phase_artifact")
        if emit_final_result:
            monitor.report_task_result(result_text)
            write_audit_event("task_result", {"result": result_text})
    except asyncio.CancelledError:
        status = "cancelled"
        reason = "cancelled"
        raise
    except (TimeoutError, asyncio.TimeoutError) as exc:
        status = "budget_exceeded"
        reason = "timeout"
        error = repr(exc)
    except PhaseBudgetExceeded as exc:
        status = "budget_exceeded"
        reason = exc.reason
        error = repr(exc)
    except ValueError as exc:
        status = "error"
        reason = str(exc).split(":", 1)[0] or "ValueError"
        error = repr(exc)
    except Exception as exc:  # noqa: BLE001 - degrade this phase and preserve later stages
        status = "error"
        reason = exc.__class__.__name__
        error = repr(exc)
    finally:
        if llm_attempted and not llm_recorded:
            run_trace.record_llm_call(phase.key, None)
        reset_research_phase_context(phase_token)
        run_trace.finish_phase(
            phase.key,
            status,
            reason,
            artifact_status="usable" if result_text else "missing",
        )

    end_data = {"result_preview": (result_text or "")[:500], **budget_data}
    if reason:
        end_data["reason"] = reason
    if error:
        end_data["error"] = error
    monitor.report_research_phase(phase.key, phase.title, status, end_data)
    write_audit_event(
        "research_phase_finished",
        {"phase_key": phase.key, "phase_title": phase.title, "status": status, **end_data},
    )
    return result_text


def _requested_artifact_formats(task_query: str) -> set[str]:
    normalized = task_query.casefold()
    formats: set[str] = set()
    if "markdown" in normalized or re.search(r"\bmd\b", normalized):
        formats.add("markdown")
    if "pdf" in normalized:
        formats.update({"markdown", "pdf"})
    return formats


def _persist_requested_artifacts(
    *, task_query: str, report_markdown: str, run_trace: ResearchRunTrace
) -> list[str]:
    """Persist requested deliverables in backend code and verify they exist."""
    formats = _requested_artifact_formats(task_query)
    created: list[str] = []
    if "markdown" not in formats:
        return created

    run_trace.record_tool_call("final_report", "write_markdown_artifact")
    md_path = write_markdown_artifact(report_markdown, "report.md")
    if not md_path.is_file() or md_path.stat().st_size == 0:
        raise RuntimeError("markdown_artifact_missing_after_write")
    created.append(str(md_path))

    if "pdf" in formats:
        run_trace.record_tool_call("final_report", "convert_md_to_pdf")
        conversion = convert_md_to_pdf.invoke(
            {"md_filename": md_path.name, "pdf_filename": "report.pdf"}
        )
        pdf_path = md_path.with_suffix(".pdf")
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            raise RuntimeError(f"pdf_artifact_missing_after_conversion: {conversion}")
        created.append(str(pdf_path))
    return created


def _classify_budget_profile(task_query: str) -> str:
    """Classify the task into a coarse execution budget profile."""
    normalized = task_query.lower()
    deep_markers = (
        "报告",
        "研报",
        "pdf",
        "markdown",
        "竞品",
        "趋势",
        "行业分析",
        "深度研究",
        "完整",
        "引用",
        "来源",
        "多源",
        "whitepaper",
        "report",
        "competitive",
        "analysis",
    )
    quick_markers = (
        "简单",
        "简短",
        "一句话",
        "快速",
        "quick",
        "brief",
    )
    if any(marker in normalized for marker in deep_markers):
        return "deep_report"
    if len(task_query) < 80 and any(marker in normalized for marker in quick_markers):
        return "quick"
    return "standard"


def _phase_thread_id(thread_id: str, phase_key: str, workflow_run_id: str) -> str:
    """Return an isolated checkpoint id for one workflow phase."""
    return f"{thread_id}__run__{workflow_run_id}__phase__{phase_key}"


def _phase_config(
    thread_id: str,
    phase_key: str,
    budget: AgentExecutionBudget,
    workflow_run_id: str = "current",
) -> dict:
    """Build the LangGraph config for one phase using its own budget."""
    return {
        "configurable": {"thread_id": _phase_thread_id(thread_id, phase_key, workflow_run_id)},
        "recursion_limit": budget.recursion_limit,
    }


def _budget_payload(
    *,
    budget: AgentExecutionBudget,
    budget_profile: str,
    remaining_workflow_seconds: float | None = None,
) -> dict:
    payload = {
        "budget_profile": budget_profile,
        "recursion_limit": budget.recursion_limit,
        "timeout_seconds": budget.timeout_seconds,
    }
    if remaining_workflow_seconds is not None:
        payload["remaining_workflow_seconds"] = max(0.0, remaining_workflow_seconds)
    return payload


def _phase_agent_for(
    *,
    phase: ResearchPhase,
    planner_agent,
    research_agent,
    writer_agent,
):
    """Select the backend-enforced capability set for a workflow phase."""
    if phase.key == "final_report":
        return writer_agent
    if phase.requires_tools:
        return research_agent
    return planner_agent


def _max_subagent_calls_for_profile(budget_profile: str) -> int:
    """Keep supervisor research from expanding into an unbounded task fan-out."""
    if budget_profile == "quick":
        return 2
    if budget_profile == "deep_report":
        return 8
    return 4


def _configured_research_subagent_names() -> frozenset[str]:
    """Return the only subagent types the research supervisor may dispatch."""
    return frozenset(agent["name"] for agent in (network_search_agent,))


async def _run_agent_phase(
    *,
    agent,
    phase: ResearchPhase,
    prompt: str,
    config: dict,
    budget: AgentExecutionBudget,
    budget_profile: str,
    research_budget: ResearchBudget,
    run_trace: ResearchRunTrace,
    remaining_workflow_seconds: float | None = None,
    max_subagent_calls: int | None = None,
    allowed_subagent_names: frozenset[str] | None = None,
    allowed_direct_tool_names: frozenset[str] | None = None,
    max_direct_tool_calls: int | None = None,
    emit_final_result: bool = False,
) -> str | None:
    """Run one enforced research phase and return the latest model text."""
    budget_data = _budget_payload(
        budget=budget,
        budget_profile=budget_profile,
        remaining_workflow_seconds=remaining_workflow_seconds,
    )
    run_trace.start_phase(phase.key, phase.title)
    if phase.requires_tools and not research_budget.take_research_round():
        run_trace.finish_phase(phase.key, "budget_exceeded", "research_round_limit")
        return None
    monitor.report_research_phase(phase.key, phase.title, "start", budget_data)
    write_audit_event(
        "research_phase_started",
        {"phase_key": phase.key, "phase_title": phase.title, **budget_data},
    )

    phase_result = None
    phase_status = "end"
    phase_error = None
    budget_reason = None
    subagent_call_count = 0
    direct_tool_call_count = 0
    phase_token = set_research_phase_context(phase.key)
    try:
        async for chunk in _astream_with_runtime_limit(
            agent,
            {"messages": [{"role": "user", "content": prompt}]},
            config,
            budget.timeout_seconds,
        ):
            # chunk 形如 {"model": {"messages": [...]}}，这里主要关心模型最新消息
            for node_name, state in chunk.items():
                if not state or "messages" not in state:
                    continue
                messages = state["messages"]
                if not (messages and isinstance(messages, list)):
                    continue
                last_msg = messages[-1]
                if node_name != "model":
                    continue

                run_trace.record_llm_call(phase.key, last_msg)
                if not research_budget.take_llm_call(phase.key):
                    raise PhaseBudgetExceeded("llm_call_limit")

                tool_calls = getattr(last_msg, "tool_calls", None)
                if tool_calls:
                    if (
                        max_direct_tool_calls is not None
                        and direct_tool_call_count + len(tool_calls) > max_direct_tool_calls
                    ):
                        # Reject the whole over-limit model batch before the tool step advances.
                        run_trace.blocked_research_tool_calls += len(tool_calls)
                        raise PhaseBudgetExceeded("local_research_query_limit")
                    direct_tool_call_count += len(tool_calls)
                    # DeepAgents 调用子智能体时，本质上会产生名为 task 的工具调用
                    for tool_call in tool_calls:
                        if (
                            allowed_direct_tool_names is not None
                            and tool_call["name"] not in allowed_direct_tool_names
                        ):
                            run_trace.blocked_research_tool_calls += 1
                            raise PhaseBudgetExceeded("research_tool_not_allowed")
                        if tool_call["name"] == "task":
                            args = tool_call.get("args") or {}
                            subagent_type = str(args.get("subagent_type") or "")
                            if (
                                allowed_subagent_names is not None
                                and subagent_type not in allowed_subagent_names
                            ):
                                raise PhaseBudgetExceeded(
                                    f"subagent_not_allowed:{subagent_type or 'missing'}"
                                )
                            if subagent_type == NETWORK_SEARCH_SUBAGENT_NAME and (
                                research_budget.available_search_queries <= 0
                                or research_budget.available_fetched_pages <= 0
                            ):
                                raise PhaseBudgetExceeded("subagent_retrieval_budget_exhausted")
                            run_trace.record_tool_call(phase.key, tool_call["name"])
                            subagent_call_count += 1
                            if (
                                max_subagent_calls is not None
                                and subagent_call_count > max_subagent_calls
                            ):
                                raise PhaseBudgetExceeded("subagent_call_limit")
                            # 子智能体调用单独上报，前端可以展示“正在调用哪个专家助手”
                            monitor.report_assistant(
                                subagent_type,
                                {"description": str(args.get("description") or "")},
                            )
                        else:
                            run_trace.record_tool_call(phase.key, tool_call["name"])
                elif last_msg.content:
                    phase_result = last_msg.content
                    if emit_final_result:
                        # 只有最终报告阶段才反馈给前端和会话历史，避免把 brief 当成最终答案
                        print(f"主智能体执行结果，最终结果：{last_msg.content[:100]}")
                        monitor.report_task_result(last_msg.content)
                        write_audit_event(
                            "task_result",
                            {"result": last_msg.content},
                        )
    except asyncio.CancelledError:
        phase_status = "cancelled"
        budget_reason = "cancelled"
        raise
    except TimeoutError as exc:
        phase_status = "budget_exceeded"
        phase_error = repr(exc)
        budget_reason = "timeout"
        message = (
            f"Research phase {phase.key} exceeded its execution budget; "
            "continuing with available evidence"
        )
        monitor._emit("phase_budget_exceeded", message, {"phase_key": phase.key, **budget_data})
        write_audit_event(
            "research_phase_budget_exceeded",
            {
                "phase_key": phase.key,
                "phase_title": phase.title,
                "reason": budget_reason,
                "error": phase_error,
                **budget_data,
            },
        )
    except PhaseBudgetExceeded as exc:
        phase_status = "budget_exceeded"
        phase_error = repr(exc)
        budget_reason = exc.reason
        message = (
            f"Research phase {phase.key} reached its {exc.reason}; "
            "continuing with available evidence"
        )
        monitor._emit("phase_budget_exceeded", message, {"phase_key": phase.key, **budget_data})
        write_audit_event(
            "research_phase_budget_exceeded",
            {
                "phase_key": phase.key,
                "phase_title": phase.title,
                "reason": budget_reason,
                "error": phase_error,
                **budget_data,
            },
        )
    except Exception as exc:
        if _is_upstream_timeout_exception(exc):
            phase_status = "budget_exceeded"
            phase_error = repr(exc)
            budget_reason = "upstream_timeout"
            run_trace.record_upstream_timeout_recovery()
            message = (
                f"Research phase {phase.key} reached an upstream model timeout; "
                "continuing with collected evidence"
            )
            monitor._emit(
                "phase_budget_exceeded",
                message,
                {"phase_key": phase.key, **budget_data},
            )
            write_audit_event(
                "research_phase_budget_exceeded",
                {
                    "phase_key": phase.key,
                    "phase_title": phase.title,
                    "reason": budget_reason,
                    "error": phase_error,
                    **budget_data,
                },
            )
        elif exc.__class__.__name__ != "GraphRecursionError":
            phase_status = "error"
            phase_error = repr(exc)
            budget_reason = exc.__class__.__name__
            raise
        else:
            phase_status = "budget_exceeded"
            phase_error = repr(exc)
            budget_reason = "recursion_limit"
            message = (
                f"Research phase {phase.key} reached its recursion budget; "
                "continuing with available evidence"
            )
            monitor._emit(
                "phase_budget_exceeded",
                message,
                {"phase_key": phase.key, **budget_data},
            )
            write_audit_event(
                "research_phase_budget_exceeded",
                {
                    "phase_key": phase.key,
                    "phase_title": phase.title,
                    "reason": budget_reason,
                    "error": phase_error,
                    **budget_data,
                },
            )
    finally:
        reset_research_phase_context(phase_token)
        run_trace.finish_phase(
            phase.key,
            phase_status,
            budget_reason,
            artifact_status="usable" if phase_result else "missing",
        )

    phase_end_data = {
        "result_preview": (phase_result or "")[:500],
        "subagent_call_count": subagent_call_count,
        **budget_data,
    }
    if phase_error:
        phase_end_data["error"] = phase_error
    if budget_reason:
        phase_end_data["reason"] = budget_reason
    monitor.report_research_phase(
        phase.key,
        phase.title,
        phase_status,
        phase_end_data,
    )
    write_audit_event(
        "research_phase_finished",
        {
            "phase_key": phase.key,
            "phase_title": phase.title,
            "status": phase_status,
            "result_preview": (phase_result or "")[:500],
            "subagent_call_count": subagent_call_count,
            **budget_data,
        },
    )
    return phase_result


def _requires_knowledge_base_first(task_query: str) -> bool:
    """Return True when the user is asking about content inside a local document."""
    document_markers = (
        "白皮书",
        "研报",
        "报告",
        "pdf",
        "PDF",
        "文档",
        "文件",
        "资料",
        "手册",
    )
    content_markers = (
        "里提到",
        "中提到",
        "提到的",
        "里面",
        "其中",
        "原文",
        "摘取",
        "提取",
        "市场份额",
        "营收",
        "收入",
        "市场规模",
    )
    return any(marker in task_query for marker in document_markers) and any(
        marker in task_query for marker in content_markers
    )


def _requires_local_knowledge_base_only(task_query: str) -> bool:
    """Return True only for affirmative local-only source intent."""
    return requires_local_only(task_query)


async def run_deep_agent(
    task_query,
    session_id,
    user_id: str | None = None,
    monitor_thread_id: str | None = None,
    conversation_memory: str = "",
    budget_profile_override: str | None = None,
    research_limits_override: ResearchBudgetLimits | None = None,
    sql_entity_recovery_enabled: bool = False,
    export_evaluation_evidence: bool = False,
    indexed_local_research_enabled: bool = False,
    required_evidence_sources: tuple[str, ...] = (),
):
    """
    异步流式执行主智能体

    API 层会为每次任务传入用户问题和 session_id。本函数负责准备会话目录、
    复制上传文件、写入 ContextVar，并在流式执行过程中把关键事件上报给前端。
    :param task_query: 前端提交的原始任务问题
    :param session_id: 当前任务 ID，同时用于 thread_id、输出目录和 WebSocket 定向推送
    """
    if any(source not in {"local_document", "web", "sql"} for source in required_evidence_sources):
        raise ValueError("Unsupported required Evidence source")
    event_thread_id = monitor_thread_id or session_id
    settings = get_settings()
    allowed_profiles = {"quick", "standard", "deep_report", "thorough"}
    budget_profile = (
        budget_profile_override
        if budget_profile_override in allowed_profiles
        else _classify_budget_profile(task_query)
    )
    workflow_run_id = uuid.uuid4().hex
    research_budget = _create_research_budget(
        task_query,
        research_limits_override or settings.research_budget_limits(budget_profile),
        sql_entity_recovery_enabled=sql_entity_recovery_enabled,
    )
    run_trace = ResearchRunTrace(
        run_id=workflow_run_id,
        thread_id=event_thread_id,
        budget_profile=budget_profile,
        budget=research_budget,
    )
    run_trace.local_retrieval_required = _requires_local_knowledge_base_only(task_query)
    run_trace.capture_claim_validation_inputs = export_evaluation_evidence
    run_trace.capture_report_source_checks = export_evaluation_evidence
    print(f"[MainAgent] 开始执行会话，session_id={session_id}")
    write_audit_event(
        "task_started",
        {
            "query": task_query,
        },
        thread_id=event_thread_id,
    )

    # 每个会话独立使用 output/session_{session_id}，避免不同用户的产物互相覆盖
    session_parent = project_root_path / "output"
    if user_id:
        session_parent = session_parent / f"user_{user_id}"
    session_dir = session_parent / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # 前端和工具使用绝对路径；提示词里只给模型相对路径，降低模型误用系统绝对路径的概率
    session_dir_str = str(session_dir).replace("\\", "/")
    relative_session_dir_str = str(session_dir.relative_to(project_root_path)).replace("\\", "/")

    # 上传文件先落在 updated/session_{session_id}，执行前复制到本次 output 工作目录
    # 这样读文件工具和生成文件工具都只需要围绕同一个 session_dir 工作
    updated_parent = project_root_path / "updated"
    if user_id:
        updated_parent = updated_parent / f"user_{user_id}"
    updated_dir_path = updated_parent / f"session_{session_id}"
    updated_info_prompt = ""
    if updated_dir_path.exists():
        files = [f.name for f in updated_dir_path.iterdir() if f.is_file()]
        if files:
            for filename in files:
                # copy2 会保留上传文件的修改时间、权限等元数据，便于后续排查文件来源
                shutil.copy2(updated_dir_path / filename, session_dir / filename)

            # 把上传文件列表注入用户消息，提醒模型先调用 read_file_content 获取附件内容
            updated_info_prompt = (
                "\n    [已上传文件] 已加载到工作目录:\n"
                + "\n".join([f"    - {f}" for f in files])
                + "\n    请优先使用工具（read_file_content）读取并参考这些文件。"
            )

    # ContextVar 让深层工具无需显式传参，也能拿到当前会话目录和 WebSocket thread_id
    session_dir_token = set_session_context(session_dir_str)
    session_id_token = set_thread_context(event_thread_id)
    user_id_token = set_user_context(user_id) if user_id else None

    monitor._emit(
        "research_run_started",
        f"研究任务使用 {budget_profile} 预算",
        {
            "run_id": workflow_run_id,
            "budget_profile": budget_profile,
            "budget": research_budget.snapshot(),
        },
    )

    # 前端拿到工作目录后，可以展示本次任务生成的 Markdown/PDF 等产物
    monitor.report_session_dir(session_dir_str)

    # checkpointer 依赖 thread_id 区分会话记忆；同一 session_id 会复用同一条执行上下文
    # 工作环境指令是运行时动态补充的，约束模型只在当前会话目录读写文件
    path_instruction = f"""
    【工作环境指令】
    工作目录: {relative_session_dir_str}
    {updated_info_prompt}

    规则：
    1. 新生成文件必须保存到工作目录：'{relative_session_dir_str}/filename'
    2. 读取已上传的文件时，请直接将文件名（例如：'开篇.txt'）作为 filename 参数传入（read_file_content）读取工具，不要带上任何目录前缀。
    3. 使用相对路径，禁止使用绝对路径
    4. 若存在上传文件，请先分析内容
    """

    source_routing_instruction = ""
    if _requires_knowledge_base_first(task_query):
        source_routing_instruction = """

    【信息源路由指令】
    用户正在询问具体白皮书、研报、报告、PDF 或文档中的内容。第一步必须调用 collect_evidence，
    使用 source=local_document 检索本地已索引文档；只有工具明确返回 NO_EVIDENCE、ERROR 或证据不足时，
    才可以调用“网络搜索助手”补充公开信息。
    """
    if _requires_local_knowledge_base_only(task_query):
        source_routing_instruction += """

    【本地知识库限定】
    用户明确要求只使用本地知识库。本轮任务禁止调用“网络搜索助手”和任何互联网搜索工具；
    只能调用 collect_evidence 的 source=local_document；如果没有找到答案或执行失败，必须直接说明
    本地知识库结果不足或失败原因，不得改用网络搜索补充。
    """

    memory_instruction = ""
    if user_id:
        try:
            memory_instruction = "\n\n" + format_memories_for_prompt(
                search_memories(user_id=user_id, query=task_query)
            )
        except Exception as exc:
            write_audit_event(
                "memory_retrieval_error",
                {"error": repr(exc)},
                thread_id=event_thread_id,
            )

    final_result = None
    run_status = "completed"
    run_failure_reason = None
    runtime_tokens = set_research_runtime(research_budget, run_trace)
    indexed_local_only = (
        indexed_local_research_enabled
        and run_trace.local_retrieval_required
        and not updated_info_prompt
    )
    run_trace.research_tool_mode = (
        "indexed_local_only" if indexed_local_only else "deepagents_default"
    )
    run_trace.research_tool_call_limit = 2 if indexed_local_only else None
    try:
        planner_agent = get_planner_agent()
        research_agent = (
            get_indexed_local_research_agent() if indexed_local_only else get_research_agent()
        )
        writer_agent = get_writer_agent()
        runtime_instructions = (
            path_instruction
            + source_routing_instruction
            + memory_instruction
            + ("\n\n" + conversation_memory if conversation_memory else "")
        )
        phase_outputs: dict[str, str] = {}
        max_subagent_calls = _max_subagent_calls_for_profile(budget_profile)

        for phase in RESEARCH_PHASES:
            remaining_workflow_seconds = research_budget.remaining_seconds
            phase_budget = settings.agent_phase_budget(phase.key, budget_profile)
            if remaining_workflow_seconds <= 0:
                reason = "run-level research budget was exhausted before this phase started"
                run_trace.start_phase(phase.key, phase.title)
                run_trace.finish_phase(
                    phase.key, "budget_exceeded", "run_timeout", artifact_status="fallback"
                )
                monitor._emit(
                    "workflow_budget_exceeded",
                    reason,
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "budget_profile": budget_profile,
                        "hard_timeout_seconds": research_budget.limits.total_seconds,
                    },
                )
                write_audit_event(
                    "workflow_budget_exceeded",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "budget_profile": budget_profile,
                        "hard_timeout_seconds": research_budget.limits.total_seconds,
                    },
                    thread_id=event_thread_id,
                )
                phase_result = build_degraded_phase_output(
                    task_query=task_query,
                    phase=phase,
                    phase_outputs=phase_outputs,
                    reason=reason,
                )
                if phase.key == "final_report":
                    phase_result = local_evidence_boundary(run_trace) or phase_result
                    phase_result, citation_validation = _enforce_final_report_citations(
                        report_markdown=phase_result,
                        compressed_fallback=phase_outputs.get("evidence_compression", ""),
                        run_trace=run_trace,
                    )
                    phase_result = _attach_required_executed_sql(phase_result, run_trace)
                    monitor.report_task_result(phase_result)
                    write_audit_event(
                        "task_result",
                        {
                            "result": phase_result,
                            "degraded": True,
                            "citation_valid": citation_validation.valid,
                            "budget_profile": budget_profile,
                        },
                        thread_id=event_thread_id,
                    )
                phase_outputs[phase.key] = phase_result
                if phase.key == "final_report":
                    final_result = phase_result
                    try:
                        _persist_requested_artifacts(
                            task_query=task_query,
                            report_markdown=phase_result,
                            run_trace=run_trace,
                        )
                        run_trace.mark_phase_artifact(phase.key, "fallback_persisted")
                    except Exception as exc:  # noqa: BLE001
                        run_trace.record_failure(exc.__class__.__name__)
                        run_trace.mark_phase_artifact(phase.key, "persistence_failed")
                continue

            phase_budget = AgentExecutionBudget(
                recursion_limit=phase_budget.recursion_limit,
                timeout_seconds=research_budget.phase_timeout(
                    phase.key,
                    phase_budget.timeout_seconds,
                ),
            )
            phase_runtime_instructions = runtime_instructions
            if indexed_local_only and phase.key == "supervisor_research":
                # Do not ask the restricted researcher to obey filesystem/delegation instructions.
                phase_runtime_instructions = ""
            if phase.key == "supervisor_research":
                if run_trace.local_retrieval_required:
                    lookup_started = asyncio.get_running_loop().time()
                    await require_local_retrieval(
                        task_query, run_trace, phase_budget.timeout_seconds
                    )
                    lookup_elapsed = asyncio.get_running_loop().time() - lookup_started
                    phase_budget = AgentExecutionBudget(
                        recursion_limit=phase_budget.recursion_limit,
                        timeout_seconds=research_budget.phase_timeout(
                            phase.key, max(0.0, phase_budget.timeout_seconds - lookup_elapsed)
                        ),
                    )
                    phase_runtime_instructions += (
                        "\n\n【后端本地取证状态】\n"
                        + json.dumps(run_trace.local_retrieval_summary(), ensure_ascii=False)
                        + "\n已有证据只代表检索返回片段，不代表足以回答所有子问题。"
                        "不得由未检索、工具失败、超时或未命中推断文档不存在。\n"
                        + run_trace.render_evidence_ledger()
                    )
                semantic_context = (
                    ""
                    if indexed_local_only
                    else await _prefetch_sql_semantic_context(
                        task_query=task_query,
                        run_trace=run_trace,
                        timeout_seconds=remaining_workflow_seconds,
                    )
                )
                if semantic_context:
                    phase_runtime_instructions = (
                        f"{phase_runtime_instructions}\n\n"
                        "【Backend SQL Semantic Context】\n"
                        "Use these pinned metric definitions, dependency formulas, resolved_columns, "
                        "and relevant_table_columns to construct SQL expressions. Never treat a "
                        "metric name as a physical column. They are discovery-only and cannot "
                        "directly support final Claims.\n\n"
                        f"{semantic_context}"
                    )
            prompt_phase_outputs = phase_outputs
            if phase.key == "evidence_compression":
                prompt_phase_outputs = _compression_phase_outputs(phase_outputs, run_trace)
            prompt = build_phase_prompt(
                task_query=task_query,
                phase=phase,
                phase_outputs=prompt_phase_outputs,
                runtime_instructions=phase_runtime_instructions,
                indexed_local_only=indexed_local_only,
            )
            if run_trace.local_retrieval_required and phase.key == "final_report":
                # Writer intentionally receives no general runtime/tool instructions.
                prompt += (
                    "\n\n【已登记本地片段来源清单：仅为来源标签，不代表全文核查】\n"
                    + json.dumps(
                        document_catalog(run_trace.local_document_records()), ensure_ascii=False
                    )
                    + "\n仅使用上述真实文件名，不得编造或缩写成新的文件名；证据不足时只说明边界。"
                    "不能据片段或检索未命中声称已逐项核查全文、全部文档或全库不存在内容。"
                )
            phase_agent = _phase_agent_for(
                phase=phase,
                planner_agent=planner_agent,
                research_agent=research_agent,
                writer_agent=writer_agent,
            )
            boundary = (
                local_evidence_boundary(run_trace)
                if phase.key in {"evidence_compression", "final_report"}
                else None
            )
            if boundary is not None:
                run_trace.start_phase(phase.key, phase.title)
                run_trace.finish_phase(phase.key, "end", artifact_status="local_evidence_boundary")
                phase_result = boundary
            elif phase.requires_tools:
                config = _phase_config(
                    event_thread_id,
                    phase.key,
                    phase_budget,
                    workflow_run_id,
                )
                phase_result = await _run_agent_phase(
                    agent=phase_agent,
                    phase=phase,
                    prompt=prompt,
                    config=config,
                    budget=phase_budget,
                    budget_profile=budget_profile,
                    research_budget=research_budget,
                    run_trace=run_trace,
                    remaining_workflow_seconds=remaining_workflow_seconds,
                    max_subagent_calls=max_subagent_calls,
                    allowed_subagent_names=frozenset()
                    if indexed_local_only
                    else _configured_research_subagent_names(),
                    allowed_direct_tool_names=frozenset({collect_local_evidence.name})
                    if indexed_local_only
                    else None,
                    max_direct_tool_calls=run_trace.research_tool_call_limit,
                )
            else:
                schema = None
                structured_renderer: Callable[[Any], str] | None = None
                if phase.key == "clarify_and_brief":
                    schema = ResearchBrief
                elif phase.key == "evidence_compression":
                    schema = CompressedEvidence
                    structured_renderer = partial(
                        _render_validated_compression,
                        run_trace=run_trace,
                    )
                phase_result = await _run_direct_phase(
                    model=phase_agent,
                    phase=phase,
                    prompt=prompt,
                    budget=phase_budget,
                    budget_profile=budget_profile,
                    research_budget=research_budget,
                    run_trace=run_trace,
                    schema=schema,
                    structured_renderer=structured_renderer,
                    emit_final_result=False,
                )
            if phase.key == "supervisor_research":
                if not indexed_local_only and _should_attempt_sql_evidence_correction(run_trace):
                    correction_config = settings.agent_phase_budget(
                        SQL_EVIDENCE_CORRECTION_PHASE.key,
                        budget_profile,
                    )
                    correction_budget = AgentExecutionBudget(
                        recursion_limit=correction_config.recursion_limit,
                        timeout_seconds=research_budget.phase_timeout(
                            SQL_EVIDENCE_CORRECTION_PHASE.key,
                            correction_config.timeout_seconds,
                        ),
                    )
                    if correction_budget.timeout_seconds > 0:
                        await _run_sql_evidence_correction(
                            model=planner_agent,
                            task_query=task_query,
                            research_brief=phase_outputs.get("clarify_and_brief", ""),
                            budget=correction_budget,
                            budget_profile=budget_profile,
                            research_budget=research_budget,
                            run_trace=run_trace,
                        )
                phase_result = _attach_backend_evidence_ledger(phase_result, run_trace)
                if not indexed_local_only:
                    phase_result = _enforce_research_evidence_requirements(phase_result, run_trace)
            if not phase_result:
                run_trace.degraded = True
                phase_result = build_degraded_phase_output(
                    task_query=task_query,
                    phase=phase,
                    phase_outputs=phase_outputs,
                    reason="phase budget was exhausted before a usable artifact was captured",
                )
                run_trace.mark_phase_artifact(phase.key, "fallback")
                monitor._emit(
                    "phase_degraded",
                    f"Using degraded artifact for phase: {phase.key}",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "result_preview": phase_result[:500],
                        "budget_profile": budget_profile,
                    },
                )
                write_audit_event(
                    "research_phase_degraded",
                    {
                        "phase_key": phase.key,
                        "phase_title": phase.title,
                        "result_preview": phase_result[:500],
                        "budget_profile": budget_profile,
                    },
                    thread_id=event_thread_id,
                )
            if phase.key == "final_report" and phase_result:
                phase_result, citation_validation = _enforce_final_report_citations(
                    report_markdown=phase_result,
                    compressed_fallback=phase_outputs.get("evidence_compression", ""),
                    run_trace=run_trace,
                )
                if required_evidence_sources:
                    phase_result, citation_validation = _enforce_required_source_delivery(
                        phase_result, citation_validation, run_trace, required_evidence_sources
                    )
                phase_result = _attach_required_executed_sql(phase_result, run_trace)
                if not citation_validation.valid:
                    run_trace.mark_phase_artifact(phase.key, "citation_rejected")
                    monitor._emit(
                        "final_report_citation_rejected",
                        "Writer output failed deterministic citation validation.",
                        {
                            "unknown_evidence_ids": list(citation_validation.unknown_evidence_ids),
                            "missing_required_citations": (
                                citation_validation.missing_required_citations
                            ),
                        },
                    )
                monitor.report_task_result(phase_result)
                write_audit_event(
                    "task_result",
                    {
                        "result": phase_result,
                        "degraded": run_trace.degraded,
                        "citation_valid": citation_validation.valid,
                        "budget_profile": budget_profile,
                    },
                    thread_id=event_thread_id,
                )
                try:
                    created_artifacts = _persist_requested_artifacts(
                        task_query=task_query,
                        report_markdown=phase_result,
                        run_trace=run_trace,
                    )
                    requested_formats = _requested_artifact_formats(task_query)
                    if requested_formats and not created_artifacts:
                        raise RuntimeError("requested_artifact_not_created")
                    if any(item["withheld"] for item in run_trace.local_scope_checks):
                        artifact_status = (
                            "scope_withheld_persisted" if requested_formats else "scope_withheld"
                        )
                    elif any(item["withheld"] for item in run_trace.local_source_reference_checks):
                        artifact_status = (
                            "source_withheld_persisted" if requested_formats else "source_withheld"
                        )
                    elif run_trace.report_citation_withheld:
                        artifact_status = (
                            "citation_withheld_persisted"
                            if requested_formats
                            else "citation_withheld"
                        )
                    elif run_trace.report_used_claim_fallback:
                        artifact_status = (
                            "validated_fallback_persisted"
                            if requested_formats
                            else "validated_fallback"
                        )
                    elif citation_validation.valid:
                        artifact_status = "persisted" if requested_formats else "usable"
                    else:
                        artifact_status = (
                            "validated_fallback_persisted"
                            if requested_formats
                            else "validated_fallback"
                        )
                    run_trace.mark_phase_artifact(phase.key, artifact_status)
                except Exception as exc:  # noqa: BLE001 - return report text but mark run degraded
                    run_trace.degraded = True
                    run_trace.record_failure(str(exc) or exc.__class__.__name__)
                    run_trace.mark_phase_artifact(phase.key, "persistence_failed")
                    monitor._emit(
                        "artifact_persistence_error",
                        "最终报告已生成，但请求的文件未能可靠落盘。",
                        {"error": repr(exc)},
                    )

            phase_outputs[phase.key] = phase_result
            if phase.key == "final_report":
                final_result = phase_result

        if not final_result:
            fallback_result = phase_outputs.get("evidence_compression") or phase_outputs.get(
                "supervisor_research"
            )
            if fallback_result:
                final_result = (
                    "本轮研究已达到当前执行预算，以下是基于已完成阶段整理的可用结果。\n\n"
                    + fallback_result
                )
                final_result, _ = _enforce_final_report_citations(
                    report_markdown=final_result,
                    compressed_fallback="",
                    run_trace=run_trace,
                )
                monitor.report_task_result(final_result)
                write_audit_event(
                    "task_result",
                    {
                        "result": final_result,
                        "degraded": True,
                        "budget_profile": budget_profile,
                    },
                    thread_id=event_thread_id,
                )

    except asyncio.CancelledError:
        run_status = "cancelled"
        run_failure_reason = "cancelled_by_user_or_eval"
        monitor.report_task_cancelled()
        write_audit_event("task_cancelled", {}, thread_id=event_thread_id)
        raise
    except TimeoutError:
        run_status = "timeout"
        run_failure_reason = "run_timeout"
        message = (
            "Agent execution exceeded the configured runtime budget. "
            "Increase the phase or hard runtime budget for larger research tasks."
        )
        monitor._emit("error", message)
        write_audit_event(
            "task_timeout",
            {
                "hard_timeout_seconds": research_budget.limits.total_seconds,
                "budget_profile": budget_profile,
            },
            thread_id=event_thread_id,
        )
    except Exception as e:
        if e.__class__.__name__ == "GraphRecursionError":
            run_status = "recursion_limit"
            run_failure_reason = "graph_recursion_limit"
            message = (
                "Agent execution reached the configured recursion budget before a "
                "phase handler could degrade gracefully."
            )
            monitor._emit("error", message)
            write_audit_event(
                "task_recursion_limit",
                {
                    "hard_recursion_limit": settings.agent_hard_max_recursion_limit,
                    "budget_profile": budget_profile,
                    "error": repr(e),
                },
                thread_id=event_thread_id,
            )
            return final_result
        run_status = "error"
        run_failure_reason = e.__class__.__name__
        # 异步执行异常也走 monitor，保证前端能收到明确错误事件
        monitor._emit("error", f"执行主智能发生异常信息：{str(e)}")
        write_audit_event("task_error", {"error": repr(e)}, thread_id=event_thread_id)
    finally:
        trace_payload = run_trace.finalize(
            status=run_status,
            final_result=final_result,
            failure_reason=run_failure_reason,
        )
        trace_path = session_dir / "research_trace.json"
        try:
            ResearchRunTrace.write(trace_path, trace_payload)
            if export_evaluation_evidence:
                ResearchRunTrace.write(
                    session_dir / "evaluation_evidence.json",
                    run_trace.export_evidence_snapshot(),
                )
            monitor._emit(
                "research_trace_complete",
                "研究运行 Trace 已生成",
                {
                    "path": str(trace_path),
                    "status": trace_payload["status"],
                    "elapsed_ms": trace_payload["elapsed_ms"],
                    "metrics": trace_payload["metrics"],
                    "waste": trace_payload["waste"],
                },
            )
            write_audit_event(
                "research_trace_complete",
                trace_payload,
                thread_id=event_thread_id,
            )
        except Exception as trace_error:
            write_audit_event(
                "research_trace_error",
                {"error": repr(trace_error)},
                thread_id=event_thread_id,
            )
        reset_research_runtime(runtime_tokens)
        # 任务结束后恢复 ContextVar，避免后续请求复用到本次会话目录或 thread_id
        reset_session_context(session_dir_token, session_id_token, user_id_token)

    return final_result


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_deep_agent("从网络查询机器人信息，并生成Markdown文件", "test_session_001"))

"""A mandatory bounded lookup, not a semantic answer or corpus-existence oracle."""

import asyncio
from time import monotonic

from app.agent.runtime import ResearchRunTrace
from app.api.audit import write_audit_event
from app.research.evidence import EvidenceRequest
from app.tools.evidence_tool import collect_evidence_request
from app.tools.local_rag_tools import _resolve_knowledge_bases


async def require_local_retrieval(query: str, trace: ResearchRunTrace, timeout: float) -> None:
    """Use the same production collector, registering only results received before deadline.

    Registry names literally mentioned in the request select mandatory lookup scopes. Without
    a recognized name, use the existing all-local scope. This is not an authorization parser.
    Timed-out synchronous work may finish in its thread, but cannot publish late Evidence here.
    """
    started = monotonic()
    deadline = started + min(60.0, max(0.0, timeout))
    if timeout <= 0:
        return
    try:
        bases = await asyncio.wait_for(
            asyncio.to_thread(_resolve_knowledge_bases, "all"),
            timeout=max(0.001, deadline - monotonic()),
        )
        scopes = [base.name for base in bases if base.name and base.name in query] or ["all"]
        for scope in scopes:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            trace.record_tool_call("supervisor_research", "collect_evidence_request")
            batch = await asyncio.wait_for(
                asyncio.to_thread(
                    collect_evidence_request,
                    EvidenceRequest(source="local_document", query=query, knowledge_base=scope),
                ),
                timeout=remaining,
            )
            trace.record_evidence(batch.records)
            trace.record_local_retrieval(batch.status.value, len(batch.records))
    except TimeoutError:
        trace.record_local_retrieval("TIMEOUT", 0)
    except Exception:  # noqa: BLE001 - source/provider errors must not become absence claims
        trace.record_local_retrieval("ERROR", 0)
    if trace.local_retrieval_summary()["had_error"]:
        trace.degraded = True
        trace.record_failure("local_retrieval_failed")
    trace.local_retrieval_required_elapsed_ms = round((monotonic() - started) * 1000)
    write_audit_event("required_local_retrieval", trace.local_retrieval_summary())


def local_evidence_boundary(trace: ResearchRunTrace) -> str | None:
    """Withhold synthesized answers when no actual local Evidence has been registered."""
    summary = trace.local_retrieval_summary()
    if not summary["required"] or summary["record_count"]:
        return None
    state = summary["state"]
    if state == "error":
        explanation = "本轮本地检索执行失败或超时，未获得可验证的本地证据。"
    elif state == "no_evidence":
        explanation = "本轮已执行有界本地检索，但没有返回可引用的相关片段。"
    else:
        explanation = "本轮未完成本地检索，尚未获得可验证的本地证据。"
    if state != "no_evidence":
        trace.degraded = True
        trace.record_failure(f"local_retrieval_{state}")
    return (
        "# 本地研究结果：证据不足\n\n## 结论\n\n"
        f"{explanation}无法基于当前证据回答原问题。\n\n"
        "## 证据分析\n\n"
        f"- 检索状态：`{state}`。\n"
        "- 未形成有证据支持的事实结论，不生成虚构引用。\n\n"
        "## 局限性\n\n"
        "该状态不代表文档不存在、未被收录或原文没有答案；有界检索不保证穷尽语料。"
        "需要核对知识库范围、检索服务状态与查询表达后再尝试。\n"
    )

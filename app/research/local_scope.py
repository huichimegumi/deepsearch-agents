"""Conservative lexical delivery gate; not a semantic support or corpus audit."""

import re

POLICY = "local_absence_wording_v1"
# Match explicit corpus/full-document scope followed by an absence predicate.
# Commas delimit clauses: a caveat elsewhere must not excuse an affirmative assertion.
SCOPE = (
    r"(?:本地)?知识库(?:中|内)?|所有(?:可访问的|已索引的|本地的)?(?:文档|资料|文件)"
    r"|全部(?:文档|资料|文件)|(?:该|这份|整份)(?:文档|报告)全文"
    r"|(?:the\s+)?(?:local\s+)?(?:knowledge\s+base|corpus)"
    r"|all\s+(?:accessible\s+|indexed\s+|local\s+)?(?:documents|files|sources)"
    r"|the\s+(?:entire|whole)\s+document"
)
ABSENCE = (
    r"(?:均|都|并)?(?:不包含|未包含|未提及|没有|不存在|未收录|不含|未涉及)"
    r"|(?:contains?\s+no|does\s+not\s+(?:contain|mention|include)"
    r"|do\s+not\s+(?:contain|mention|include)|never\s+mentions?)\b"
)
ASSERTION = re.compile(rf"(?:{SCOPE})\s*(?:中|内)?\s*(?:{ABSENCE})", re.I)
SAFE_PREFIX = re.compile(
    r"(?:无法|不能|尚不能|不能据此)(?:确认|确定|断言|证明)\s*[‘'“\"]?$"
    r"|(?:cannot|can't|unable\s+to)\s+(?:confirm|conclude|establish|prove)\s+(?:that\s+)?$",
    re.I,
)


def check_local_absence_scope(report: str) -> dict:
    """Return private candidate spans. Unmatched text is unreviewed, never 'supported'."""
    findings = []
    # Formatting must not hide the observed bolded Chinese assertion.
    plain = re.sub(r"[*_`]+", "", report)
    for clause in re.split(r"[。！？!?；;，,\n]", plain):
        for match in ASSERTION.finditer(clause):
            if not SAFE_PREFIX.search(clause[: match.start()]):
                findings.append(match.group(0))
    return {"policy": POLICY, "matched_assertions": findings}


def enforce_local_absence_scope(report: str, trace, *, candidate_kind: str) -> str | None:
    if not trace.local_retrieval_required:
        return None
    audit = check_local_absence_scope(report)
    count = len(audit["matched_assertions"])
    trace.local_scope_checks.append(
        {
            "policy": POLICY,
            "candidate_kind": candidate_kind,
            "matches": count,
            "withheld": bool(count),
        }
    )
    if trace.capture_report_source_checks:
        trace._local_scope_checks_private.append(
            {"candidate_kind": candidate_kind, "candidate_report": report, **audit}
        )
    if not count:
        return None
    trace.degraded = True
    trace.record_failure("unverified_local_absence_scope")
    return (
        "# 本地报告：结论范围核验不足\n\n"
        "生成正文含有将检索结果扩大为知识库或全文缺失结论的明确措辞，已停止交付该正文。\n\n"
        "本轮只取得有限的检索片段，未执行可证明覆盖范围的全文或全库审计。"
        "当前证据不足以判断相关内容是否存在；检索未命中和片段未提及都不能证明其不存在。\n\n"
        "## 后续核验\n\n"
        "需要核对目标文档、章节及实际覆盖范围后再回答。此说明不构成原问题的事实答案，"
        "也不代表相关文件或章节不存在。\n"
    )

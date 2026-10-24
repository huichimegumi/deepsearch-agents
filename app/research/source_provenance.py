"""Deterministic filename identity checks, not semantic or exhaustive-corpus validation."""

import json
import re
import unicodedata
from collections.abc import Iterable

EXPLICIT_FILENAME = re.compile(r"《([^《》\n]{1,240}\.(?:pdf|docx?|xlsx?|txt|md))》", re.I)


def filename_key(name: str) -> str:
    return unicodedata.normalize("NFC", name.strip()).casefold()


def document_catalog(records: Iterable) -> list[dict]:
    catalog = {}
    for record in records:
        data = (
            record
            if isinstance(record, dict)
            else {
                "source": str(
                    getattr(getattr(record, "source", ""), "value", getattr(record, "source", ""))
                ),
                "metadata": getattr(record, "metadata", {}),
                "evidence_id": getattr(record, "evidence_id", ""),
            }
        )
        if data.get("source") != "local_document":
            continue
        filename = (data.get("metadata") or {}).get("filename")
        if not isinstance(filename, str) or not filename.strip() or not data.get("evidence_id"):
            continue
        key = filename_key(filename)
        item = catalog.setdefault(key, {"filename": filename, "evidence_ids": []})
        if data["evidence_id"] not in item["evidence_ids"]:
            item["evidence_ids"].append(data["evidence_id"])
    return [catalog[key] for key in sorted(catalog)]


def check_source_filenames(report: str, catalog: list[dict]) -> dict:
    names = list(dict.fromkeys(EXPLICIT_FILENAME.findall(report)))
    allowed = {filename_key(item["filename"]) for item in catalog}
    return {
        "mentioned_filenames": names,
        "unverified_filenames": [name for name in names if filename_key(name) not in allowed],
    }


def enforce_local_source_references(report: str, trace, *, candidate_kind: str) -> str | None:
    if not trace.local_retrieval_required:
        return None
    catalog = document_catalog(trace.local_document_records())
    audit = check_source_filenames(report, catalog)
    unknown = audit["unverified_filenames"]
    trace.local_source_reference_checks.append(
        {
            "candidate_kind": candidate_kind,
            "filename_mentions": len(audit["mentioned_filenames"]),
            "unverified_mentions": len(unknown),
            "withheld": bool(unknown),
        }
    )
    if trace.capture_report_source_checks:
        trace._source_reference_checks_private.append(
            {
                "candidate_kind": candidate_kind,
                "candidate_report": report,
                "catalog": catalog,
                **audit,
            }
        )
    if not unknown:
        return None
    trace.degraded = True
    trace.record_failure("unverified_local_source_filename")
    # No Claims or source-content assertions are copied from the rejected candidate/fallback.
    names = json.dumps([item["filename"] for item in catalog], ensure_ascii=False)
    return (
        "# 本地报告：来源核验未通过\n\n## 结论\n\n"
        "原生成正文包含无法映射到本轮已登记本地证据的文件名，已停止交付该正文。"
        "这不表示相关文件不存在，也不表示原问题无答案；当前不能把该报告作为有来源支持的回答。\n\n"
        "## 已登记的片段来源\n\n"
        + "```json\n"
        + names.replace("`", "\\u0060")
        .replace("<", "\\u003c")
        .replace("《", "\\u300a")
        .replace("》", "\\u300b")
        + "\n```"
        + "\n\n## 局限性\n\n"
        "此清单只表示本轮实际取回片段的来源标签，不代表读取全文、核查全部知识库或附件。"
        "未核验文件名及原报告的结论不在此重述；需要核对来源身份与证据支持后再生成回答。\n"
    )

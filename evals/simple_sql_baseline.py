"""One-pass SQL evidence and writer baseline for public DABStep tasks."""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.llm import get_model
from app.research.evidence.models import EvidenceRecord, EvidenceSource
from app.tools.evidence_tool import _collect_sqlite
from evals.benchmark_preflight import DABSTEP_DATABASE
from evals.case_worker_v3 import _dabstep_prompt
from evals.dabstep.common import default_data_dir
from evals.dabstep.fee_aggregates import DIMENSIONS
from evals.dabstep.fee_aggregates import OUTPUT as FEE_AGGREGATES

QUERIES = (
    "SELECT COUNT(*) AS transactions, COUNT(DISTINCT psp_reference) AS distinct_references, "
    "COUNT(DISTINCT merchant) AS merchants, ROUND(SUM(eur_amount), 2) AS total_eur, "
    "ROUND(AVG(eur_amount), 2) AS average_eur, SUM(has_fraudulent_dispute) AS fraud_count, "
    "SUM(is_refused_by_adyen) AS refused_count, MIN(transaction_date) AS first_date, "
    "MAX(transaction_date) AS last_date FROM payments",
    "SELECT merchant, COUNT(*) AS transactions, ROUND(SUM(eur_amount), 2) AS total_eur, "
    "SUM(has_fraudulent_dispute) AS fraud_count, SUM(is_refused_by_adyen) AS refused_count, "
    "SUM(intracountry) AS intracountry_count FROM payments GROUP BY merchant ORDER BY merchant",
    "SELECT aci, COUNT(*) AS transactions, ROUND(SUM(eur_amount), 2) AS total_eur, "
    "SUM(has_fraudulent_dispute) AS fraud_count FROM payments GROUP BY aci ORDER BY transactions DESC",
    "SELECT card_scheme, COUNT(*) AS transactions, ROUND(SUM(eur_amount), 2) AS total_eur "
    "FROM payments GROUP BY card_scheme ORDER BY transactions DESC",
    "SELECT transaction_month, COUNT(*) AS transactions, ROUND(SUM(eur_amount), 2) AS total_eur "
    "FROM payments GROUP BY transaction_month ORDER BY transaction_month",
    "SELECT SUM(CASE WHEN aci IS NULL THEN 1 ELSE 0 END) AS missing_aci, "
    "SUM(CASE WHEN ip_address IS NULL THEN 1 ELSE 0 END) AS missing_ip, "
    "SUM(CASE WHEN email_address IS NULL THEN 1 ELSE 0 END) AS missing_email, "
    "SUM(CASE WHEN is_credit IS NULL THEN 1 ELSE 0 END) AS missing_credit FROM payments",
    "SELECT m.merchant, m.account_type, m.merchant_category_code AS mcc, m.capture_delay, "
    "COUNT(p.psp_reference) AS transactions FROM merchants m LEFT JOIN payments p "
    "ON p.merchant = m.merchant GROUP BY m.merchant, m.account_type, "
    "m.merchant_category_code, m.capture_delay ORDER BY m.merchant",
    "SELECT COUNT(*) AS fee_rule_count, SUM(CASE WHEN aci IS NULL THEN 1 ELSE 0 END) "
    "AS wildcard_aci_rules, SUM(CASE WHEN intracountry IS NULL THEN 1 ELSE 0 END) "
    "AS wildcard_country_rules FROM fee_rules",
)


def collect_public_evidence(
    database: Path = DABSTEP_DATABASE, *, include_fee: bool = True
) -> list[dict]:
    records = []
    for query in QUERIES:
        batch = _collect_sqlite(query, "query", database)
        if str(batch.status) not in {"OK", "PARTIAL"}:
            raise RuntimeError(f"sql_evidence_{batch.status}")
        records.extend(record.to_dict() for record in batch.records)
    if not include_fee:
        return records
    aggregates = json.loads(FEE_AGGREGATES.read_text(encoding="utf-8"))
    if aggregates["dataset_revision"] != default_data_dir().name:
        raise ValueError("fee_aggregate_revision_mismatch")
    for dimension in DIMENSIONS:
        record = EvidenceRecord.create(
            source=EvidenceSource.FEE_ENGINE,
            locator=(f"fee://{aggregates['dataset_fingerprint']}/aggregates/{dimension}"),
            identity={
                "dataset_fingerprint": aggregates["dataset_fingerprint"],
                "dimension": dimension,
            },
            content={
                "scope": aggregates["scope"],
                "fee_formula": aggregates["fee_formula"],
                "reference_matched_fee_total_eur": aggregates["reference_matched_fee_total_eur"],
                "group_by": dimension,
                "rows": aggregates["groups"][dimension],
            },
            metadata={"evidence_kind": "validated_fee_aggregate"},
        )
        records.append(record.to_dict())
    return records


async def execute(case_id: str, *, include_fee: bool = True) -> dict:
    if not case_id.startswith("dabstep_research_"):
        raise ValueError("simple_sql_baseline_only_supports_dabstep")
    evidence = collect_public_evidence(include_fee=include_fee)
    evidence_context = "\n".join(
        f"[{record['evidence_id']}] {json.dumps(record['content'], ensure_ascii=False)}"
        for record in evidence
    )
    system_prompt = (
        "You are a careful payments analyst. Answer the task using only the public "
        "manual and the actual read-only SQL Evidence. Cite an exact Evidence ID "
        "for every numerical claim. If a fee total or counterfactual saving was not "
        "calculated, say so rather than inventing it. "
    )
    if include_fee:
        system_prompt += (
            "Fee aggregate Evidence includes only matched rules; unpriced transactions "
            "have unknown fees, not zero fees. Compare merchant, ACI, scheme, and "
            "domestic groups but do not claim observational differences are causal "
            "or project savings without a defined counterfactual. "
        )
    system_prompt += "Keep a complete report within the available output budget. Do not call tools."
    response = (
        await get_model()
        .bind(max_tokens=8000)
        .ainvoke(
            [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": _dabstep_prompt(case_id)
                    + "\n\nActual SQL Evidence:\n"
                    + evidence_context,
                },
            ]
        )
    )
    answer = response.content if isinstance(response.content, str) else str(response.content)
    return {
        "id": case_id,
        "status": "completed" if answer.strip() else "failed",
        "answer": answer,
        "evidence": evidence,
        "response_metadata": {
            "model_name": response.response_metadata.get("model_name"),
            "finish_reason": response.response_metadata.get("finish_reason"),
            "usage_metadata": response.usage_metadata,
        },
    }

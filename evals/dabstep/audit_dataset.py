from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from evals.dabstep.common import (
    HERE,
    LOCK_PATH,
    SELECTION_PATH,
    default_data_dir,
    load_json,
    load_jsonl,
    verify_files,
)

ACI_DOMAIN = set("ABCDEFG")
ACCOUNT_TYPE_DOMAIN = set("RDHFSO")


def _int_dict(values: dict[str, Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in values.items()}


def _build_selected_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selection = load_json(SELECTION_PATH)
    by_id = {row["id"]: row for row in rows}
    selected: list[dict[str, Any]] = []
    for choice in selection["tasks"]:
        source = by_id[choice["id"]]
        reference_checks = ["dataset_overview", "merchant_summary", "routing_summary"]
        if source["type"] == "Data Preparation":
            reference_checks.append("data_quality")
        selected.append(
            {
                "benchmark_id": f"dabstep_research_{source['id']:03d}",
                "source_id": source["id"],
                "split": choice["split"],
                "type": source["type"],
                "files": source["files"],
                "question": source["question"],
                "checklist": source["checklist"],
                "answerability": choice["answerability"],
                "selection_reason": choice["selection_reason"],
                "known_limitations": choice["known_limitations"],
                "required_reference_checks": reference_checks,
            }
        )
    return selected


def audit(data_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    integrity_errors = verify_files(data_dir)
    if integrity_errors:
        raise RuntimeError("locked dataset verification failed:\n" + "\n".join(integrity_errors))

    context = data_dir / "context"
    tasks = load_jsonl(data_dir / "dabstep_research.jsonl")
    payments = pd.read_csv(context / "payments.csv")
    merchants = pd.DataFrame(load_json(context / "merchant_data.json"))
    fees = pd.DataFrame(load_json(context / "fees.json"))
    acquirers = pd.read_csv(context / "acquirer_countries.csv").drop(
        columns=["Unnamed: 0"], errors="ignore"
    )
    mcc = pd.read_csv(context / "merchant_category_codes.csv").drop(
        columns=["Unnamed: 0"], errors="ignore"
    )

    dates = pd.to_datetime(payments["year"].astype(str), format="%Y") + pd.to_timedelta(
        payments["day_of_year"] - 1, unit="D"
    )
    task_types = Counter(row["type"] for row in tasks)
    normalized_questions = Counter(" ".join(row["question"].lower().split()) for row in tasks)
    active_merchants = set(payments["merchant"].unique())
    metadata_merchants = set(merchants["merchant"].unique())
    observed_mccs = set(
        merchants.loc[merchants["merchant"].isin(active_merchants), "merchant_category_code"]
    )
    known_mccs = set(mcc["mcc"])
    observed_acquirer_codes = set(payments["acquirer_country"].unique())
    mapped_acquirer_codes = set(acquirers["country_code"].unique())

    fee_mccs = {item for values in fees["merchant_category_code"] for item in values}
    selected = _build_selected_tasks(tasks)
    audit_result: dict[str, Any] = {
        "audit_version": 1,
        "dataset_revision": load_json(LOCK_PATH)["revision"],
        "integrity": {"locked_files": len(load_json(LOCK_PATH)["files"]), "errors": []},
        "tasks": {
            "total": len(tasks),
            "by_type": dict(sorted(task_types.items())),
            "empty_checklist_ids": [row["id"] for row in tasks if not row["checklist"].strip()],
            "exact_duplicate_question_groups": sum(
                1 for count in normalized_questions.values() if count > 1
            ),
            "all_tasks_use_same_file_set": len({tuple(row["files"]) for row in tasks}) == 1,
            "selected_ids": [row["source_id"] for row in selected],
            "selected_by_split": _int_dict(Counter(row["split"] for row in selected)),
            "selected_by_type": _int_dict(Counter(row["type"] for row in selected)),
            "selected": [
                {
                    "source_id": row["source_id"],
                    "split": row["split"],
                    "type": row["type"],
                    "answerability": row["answerability"],
                }
                for row in selected
            ],
        },
        "payments": {
            "rows": len(payments),
            "columns": len(payments.columns),
            "unique_psp_references": int(payments["psp_reference"].nunique()),
            "duplicate_rows": int(payments.duplicated().sum()),
            "date_min": dates.min().date().isoformat(),
            "date_max": dates.max().date().isoformat(),
            "years": sorted(int(value) for value in payments["year"].unique()),
            "null_counts": _int_dict(payments.isna().sum().to_dict()),
            "invalid_aci_rows": int((~payments["aci"].isin(ACI_DOMAIN)).sum()),
            "invalid_day_of_year_rows": int((~payments["day_of_year"].between(1, 366)).sum()),
        },
        "cross_source": {
            "transaction_merchants": len(active_merchants),
            "merchant_metadata_rows": len(merchants),
            "transactions_without_merchant_metadata": int(
                (~payments["merchant"].isin(metadata_merchants)).sum()
            ),
            "unused_merchant_metadata_rows": len(metadata_merchants - active_merchants),
            "active_merchant_mccs_missing_from_reference": sorted(observed_mccs - known_mccs),
            "invalid_account_type_rows": int(
                (~merchants["account_type"].isin(ACCOUNT_TYPE_DOMAIN)).sum()
            ),
            "observed_payment_acquirer_country_codes": sorted(observed_acquirer_codes),
            "mapped_acquirer_country_codes": sorted(mapped_acquirer_codes),
            "payment_rows_with_country_not_in_acquirer_mapping": int(
                (~payments["acquirer_country"].isin(mapped_acquirer_codes)).sum()
            ),
        },
        "fee_rules": {
            "rows": len(fees),
            "unique_ids": int(fees["ID"].nunique()),
            "null_wildcards": _int_dict(fees.isna().sum().to_dict()),
            "empty_list_wildcards": {
                column: int(fees[column].map(len).eq(0).sum())
                for column in ("account_type", "merchant_category_code", "aci")
            },
            "fee_mccs_missing_from_reference": sorted(fee_mccs - known_mccs),
            "formula_documented": "fixed_amount + rate * transaction_value / 10000",
        },
        "answerability_gaps": [
            "No realized fee column or authoritative worked example exists in this snapshot.",
            "The manual documents null as wildcard, while fees.json also uses empty lists as apparent wildcards.",
            "Transactions contain acquirer country codes but not acquirer names, so merchant-to-acquirer usage cannot be reconstructed.",
            "No processing latency or system-performance telemetry exists.",
            "Refusal is available as an authorization proxy; a full conversion funnel is not.",
            "Counterfactual savings and fraud-prevention ROI require assumptions not present in the data.",
        ],
    }
    return audit_result, selected


def render_markdown(result: dict[str, Any]) -> str:
    tasks = result["tasks"]
    payments = result["payments"]
    cross = result["cross_source"]
    fees = result["fee_rules"]
    gaps = "\n".join(f"- {item}" for item in result["answerability_gaps"])
    selected_rows = "\n".join(
        f"| {row['source_id']} | {row['split']} | {row['type']} | {row['answerability']} |"
        for row in tasks["selected"]
    )
    missing_fee_mccs = ", ".join(str(value) for value in fees["fee_mccs_missing_from_reference"])
    return f"""# DABStep-Research 数据审计

数据版本：`{result["dataset_revision"]}`。审计脚本首先验证 {result["integrity"]["locked_files"]} 个源文件的字节数和 SHA-256，当前全部通过。

## 结论

- 任务共 {tasks["total"]} 个，五类各 20 个；Open 类的 20 个任务全部缺少 checklist，不进入第一阶段子集。
- 第一阶段固定 8 个任务：dev 2 个、holdout 6 个，覆盖 Data Preparation、Data Analysis、Data Insight、Report Generation。
- `payments.csv` 有 {payments["rows"]:,} 行、{payments["columns"]} 列，`psp_reference` 全部唯一，无重复整行，日期范围为 {payments["date_min"]} 至 {payments["date_max"]}。
- 交易表只有 {cross["transaction_merchants"]} 个活跃商户；商户元数据有 {cross["merchant_metadata_rows"]} 行，其中 {cross["unused_merchant_metadata_rows"]} 行未出现在交易中。活跃交易均能关联商户元数据，活跃商户 MCC 均在参考表中。
- `fees.json` 有 {fees["rows"]} 条唯一规则。手册只明确说明 `null` 是通配符，但规则中还存在空列表；手续费精确总额必须等独立规则引擎核验后才作为硬指标。
- 费率规则引用了 {len(fees["fee_mccs_missing_from_reference"])} 个 MCC 参考表中不存在的代码（{missing_fee_mccs}）；当前 5 个活跃商户不受此问题影响，但规则库并非完全自洽。
- `acquirer_countries.csv` 是“收单机构名称 → 国家”的映射，而交易表只有国家代码；无法从当前快照还原每笔交易实际使用了哪个收单机构。
- 上游仓库未声明许可证。锁文件只用于可复现下载，原始数据保持 Git 忽略，在许可证澄清前不随项目再分发。

## 固定任务子集

| Source ID | Split | 类型 | 可回答性 |
| ---: | --- | --- | --- |
{selected_rows}

## 数据质量快照

| 检查 | 结果 |
| --- | ---: |
| 交易行数 | {payments["rows"]:,} |
| 唯一交易 ID | {payments["unique_psp_references"]:,} |
| 重复整行 | {payments["duplicate_rows"]} |
| 缺失 IP 哈希 | {payments["null_counts"]["ip_address"]:,} |
| 缺失邮箱哈希 | {payments["null_counts"]["email_address"]:,} |
| 非法 ACI | {payments["invalid_aci_rows"]} |
| 交易商户无法关联元数据 | {cross["transactions_without_merchant_metadata"]} |
| 活跃商户 MCC 不在参考表 | {len(cross["active_merchant_mccs_missing_from_reference"])} |
| 收单国家不在机构映射中的交易 | {cross["payment_rows_with_country_not_in_acquirer_mapping"]:,} |

观察到的交易收单国家：{", ".join(cross["observed_payment_acquirer_country_codes"])}。
机构映射覆盖的国家：{", ".join(cross["mapped_acquirer_country_codes"])}。

## 可回答性边界

{gaps}

## 子集使用规则

- 只用 dev 任务调 prompt、工具和工作流；holdout 只用于里程碑验收。
- 原始问题、checklist、文件列表和 source ID 原样保留；新增字段只描述 split、可回答性和已知限制。
- SQL 参考结果只覆盖可确定事实。涉及手续费匹配、因果判断和反事实节省额时，报告必须标注假设及证据边界。
- Agent 运行时只能读取源数据和任务；`reference_results.json` 只供离线 evaluator 使用。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the pinned DABStep-Research snapshot.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--output-dir", type=Path, default=HERE)
    args = parser.parse_args()

    result, selected = audit(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "audit_snapshot.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "AUDIT.md").write_text(render_markdown(result), encoding="utf-8")
    (args.output_dir / "selected_tasks.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected),
        encoding="utf-8",
    )
    print(f"wrote audit and {len(selected)} selected tasks to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

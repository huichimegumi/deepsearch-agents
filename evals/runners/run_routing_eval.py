"""Run a lightweight deterministic routing eval over boundary samples.

This runner does not call the LLM. It is a cheap baseline that checks whether
the project's intended routing rules are represented by deterministic signals.
Use it before costlier end-to-end agent evals.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evals" / "datasets" / "routing_boundary_zh.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def predict_routes(task: str) -> list[str]:
    """Predict routes using transparent rules for a first-pass baseline."""
    routes: set[str] = set()

    refusal_markers = (
        "删除",
        "DROP TABLE",
        "drop table",
        "API key",
        "api key",
        "数据库密码",
        "环境变量",
        "登录",
        "提交企业资料",
        "上周发给你",
    )
    destructive_sql_markers = ("DROP TABLE", "drop table")
    if any(marker in task for marker in refusal_markers):
        routes.add("refusal")

    refusal_only_markers = (
        "全部删除",
        "数据库密码",
        "API key",
        "api key",
        "环境变量",
        "登录",
        "提交企业资料",
        "上周发给你",
    )
    if any(marker in task for marker in refusal_only_markers):
        return ["refusal"]

    if "上传" in task or "Excel" in task or "附件" in task:
        routes.add("file_read")

    if "记住" in task or "偏好" in task:
        routes.add("memory")
        routes.add("direct_answer")

    direct_markers = ("改写", "更正式")
    if any(marker in task for marker in direct_markers):
        routes.add("direct_answer")

    db_markers = (
        "业务数据库",
        "数据库",
        "库存",
        "销售",
        "销售额",
        "销售情况",
        "内部销售",
        "公司业务表现",
        "表现如何",
    )
    if any(marker in task for marker in db_markers) and not any(
        marker in task for marker in ("不要使用公司数据库", "不使用公司数据库")
    ):
        routes.add("database_query")

    web_markers = (
        "最新",
        "公开",
        "政策",
        "监管",
        "市场",
        "趋势",
        "检索",
        "搜索",
        "CEO",
        "临床",
        "适应症",
        "跨境数据",
    )
    if any(marker in task for marker in web_markers) and not any(
        marker in task for marker in ("不要使用网络搜索", "不要联网", "只根据业务数据库")
    ):
        routes.add("network_search")

    local_only_markers = ("只使用本地知识库", "只用本地知识库", "本地知识库")
    if any(marker in task for marker in local_only_markers):
        routes.add("knowledge_base")
        routes.discard("network_search")
        routes.discard("database_query")

    report_markers = ("Markdown", "PDF", "报告", "简报", "复盘")
    if any(marker in task for marker in report_markers):
        routes.add("report_generation")

    if any(marker in task for marker in destructive_sql_markers):
        routes.add("database_query")

    if not routes:
        routes.add("direct_answer")

    return sorted(routes)


def score_row(row: dict) -> dict:
    expected = set(row["expected_route"])
    disallowed = set(row["disallowed_routes"])
    predicted = set(predict_routes(row["task"]))
    missing = sorted(expected - predicted)
    unexpected = sorted(predicted & disallowed)
    return {
        "id": row["id"],
        "expected": sorted(expected),
        "predicted": sorted(predicted),
        "missing": missing,
        "disallowed_used": unexpected,
        "passed": not missing and not unexpected,
    }


def run(dataset: Path) -> dict:
    rows = load_jsonl(dataset)
    results = [score_row(row) for row in rows]
    passed = sum(1 for item in results if item["passed"])
    violations = sum(1 for item in results if item["disallowed_used"])
    return {
        "dataset": str(dataset),
        "total": len(results),
        "passed": passed,
        "route_accuracy": passed / len(results) if results else 0.0,
        "disallowed_route_violations": violations,
        "failures": [item for item in results if not item["passed"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic routing eval.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run(args.dataset)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {report['dataset']}")
        print(f"Total: {report['total']}")
        print(f"Passed: {report['passed']}")
        print(f"Route accuracy: {report['route_accuracy']:.1%}")
        print(f"Disallowed route violations: {report['disallowed_route_violations']}")
        if report["failures"]:
            print("\nFailures:")
            for item in report["failures"]:
                print(
                    f"- {item['id']}: expected={item['expected']} "
                    f"predicted={item['predicted']} missing={item['missing']} "
                    f"disallowed_used={item['disallowed_used']}"
                )
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

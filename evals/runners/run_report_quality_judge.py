"""Lightweight LLM-as-a-judge scoring for generated report artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.llm import get_model
from app.agent.main_agent import project_root_path
from evals.runners.common import DATASET_DIR, RESULTS_DIR, load_jsonl, now_utc, write_json


DEFAULT_DATASET = DATASET_DIR / "end_to_end_report_zh.jsonl"
MAX_REPORT_CHARS = 24000

JUDGE_SYSTEM_PROMPT = """你是一个严格但公正的中文商业/技术报告质量评审员。
你只能基于用户任务、必需章节和报告正文评分，不要使用外部知识，不要做事实查证。
本轮不评估搜索来源真实性、数据库数字准确性或 RAG 证据对齐，只评估报告文本本身的质量。

请按以下维度给分，总分 100：
- task_completion: 0-30，报告是否完成用户任务、覆盖核心问题。
- required_sections: 0-20，是否包含并实质性覆盖必需章节。
- actionability: 0-25，建议、清单、结论是否具体可执行，是否能指导下一步。
- writing_quality: 0-25，结构、表达、专业性、冗余控制、可读性。

只输出 JSON，不要输出 Markdown，不要添加解释性前后缀。
JSON schema:
{
  "task_completion": 0,
  "required_sections": 0,
  "actionability": 0,
  "writing_quality": 0,
  "total": 0,
  "grade": "excellent|good|fair|poor",
  "major_issues": ["..."],
  "strengths": ["..."],
  "summary": "一句话中文评价"
}
"""


def _artifact_dir(sample_id: str) -> Path:
    return project_root_path / "output" / "user_evals" / f"session_eval_{sample_id}"


def _find_report_artifacts(sample_id: str) -> list[Path]:
    output_dir = _artifact_dir(sample_id)
    if not output_dir.exists():
        return []
    return sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".pdf"}
    )


def _select_readable_artifact(artifacts: list[Path]) -> Path | None:
    markdowns = [path for path in artifacts if path.suffix.lower() == ".md"]
    if markdowns:
        return max(markdowns, key=lambda path: path.stat().st_size)
    return None


def _read_report_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= MAX_REPORT_CHARS:
        return text
    return text[:MAX_REPORT_CHARS] + "\n\n[内容因评测预算被截断]"


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = minimum
    return min(maximum, max(minimum, number))


def _normalize_judge_result(payload: dict[str, Any]) -> dict[str, Any]:
    scores = {
        "task_completion": _bounded_int(payload.get("task_completion"), 0, 30),
        "required_sections": _bounded_int(payload.get("required_sections"), 0, 20),
        "actionability": _bounded_int(payload.get("actionability"), 0, 25),
        "writing_quality": _bounded_int(payload.get("writing_quality"), 0, 25),
    }
    total = sum(scores.values())
    if total >= 90:
        grade = "excellent"
    elif total >= 75:
        grade = "good"
    elif total >= 60:
        grade = "fair"
    else:
        grade = "poor"
    return {
        **scores,
        "total": total,
        "grade": str(payload.get("grade") or grade),
        "major_issues": [str(item) for item in payload.get("major_issues", [])][:5],
        "strengths": [str(item) for item in payload.get("strengths", [])][:5],
        "summary": str(payload.get("summary", ""))[:500],
    }


def _build_user_prompt(sample: dict[str, Any], report_text: str) -> str:
    required_sections = "、".join(sample.get("required_sections", []))
    return f"""用户任务：
{sample["task"]}

必需章节：
{required_sections or "无"}

报告正文：
{report_text}
"""


def judge_report(sample: dict[str, Any], report_text: str) -> dict[str, Any]:
    model = get_model()
    response = model.invoke(
        [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(sample, report_text)},
        ]
    )
    payload = _extract_json_object(str(response.content))
    return _normalize_judge_result(payload)


def run(dataset: Path = DEFAULT_DATASET) -> dict[str, Any]:
    samples = load_jsonl(dataset)
    results: list[dict[str, Any]] = []

    for sample in samples:
        artifacts = _find_report_artifacts(sample["id"])
        readable = _select_readable_artifact(artifacts)
        row = {
            "id": sample["id"],
            "task": sample["task"],
            "required_sections": sample.get("required_sections", []),
            "artifacts": [
                str(path.relative_to(project_root_path)).replace("\\", "/") for path in artifacts
            ],
        }
        if not readable:
            row.update(
                {
                    "status": "missing_artifact",
                    "score": 0,
                    "grade": "missing",
                    "reason": "No Markdown artifact found for lightweight text judging.",
                }
            )
            results.append(row)
            continue

        try:
            report_text = _read_report_text(readable)
            judge = judge_report(sample, report_text)
            row.update(
                {
                    "status": "judged",
                    "judged_artifact": str(readable.relative_to(project_root_path)).replace(
                        "\\", "/"
                    ),
                    "report_chars": len(report_text),
                    "score": judge["total"],
                    "judge": judge,
                }
            )
        except Exception as exc:  # noqa: BLE001 - eval should record failures
            row.update(
                {
                    "status": "judge_failed",
                    "score": 0,
                    "grade": "judge_failed",
                    "reason": repr(exc),
                }
            )
        results.append(row)

    judged_scores = [row["score"] for row in results if row["status"] == "judged"]
    all_scores = [row["score"] for row in results]
    status_counts: dict[str, int] = {}
    for row in results:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    return {
        "name": "end_to_end_report_quality_judge_zh",
        "dataset": str(dataset),
        "generated_at": now_utc(),
        "total": len(results),
        "status_counts": dict(sorted(status_counts.items())),
        "artifact_coverage": len(judged_scores) / len(results) if results else 0.0,
        "average_score_on_available": sum(judged_scores) / len(judged_scores)
        if judged_scores
        else 0.0,
        "average_score_all_samples": sum(all_scores) / len(all_scores) if all_scores else 0.0,
        "rubric": {
            "task_completion": 30,
            "required_sections": 20,
            "actionability": 25,
            "writing_quality": 25,
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight report quality LLM judge.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "report_quality_judge_eval.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.dataset)
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {report['dataset']}")
        print(f"Total: {report['total']}")
        print(f"Status counts: {report['status_counts']}")
        print(f"Artifact coverage: {report['artifact_coverage']:.1%}")
        print(f"Average score on available: {report['average_score_on_available']:.1f}/100")
        print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

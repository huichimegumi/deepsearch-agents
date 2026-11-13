"""Export saved DeepResearch Bench reports and published criteria as OSODT judge inputs.

Each run directory becomes one document per task: ``ReportN/Doc_00K.docx`` where K is the
position of the run on the command line. Report text is copied line by line without edits
or truncation, including evidence identifiers and reports from runs that did not complete.
Rubrics are the upstream criteria rows, unchanged. No model is called.
"""

import argparse
import json
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = "data/criteria_data/criteria.jsonl"


def drb_reports(run):
    """Map DRB task number to the saved report of one workflow run."""
    found = {}
    for case in sorted(p for p in run.iterdir() if p.is_dir()):
        attempts = sorted(case.glob("attempt-*"))
        if not attempts:
            continue
        attempt = attempts[-1]
        record = attempt / "worker_result.json"
        if not record.is_file():
            continue
        worker = json.loads(record.read_bytes())
        suite, _, number = str(worker.get("case_id") or worker.get("id") or "").partition(":")
        if suite != "drb":
            continue
        result = attempt / "research_result.json"
        status = json.loads(result.read_bytes()).get("status") if result.is_file() else None
        report = attempt / "report.md"
        found[int(number)] = {
            "status": status,
            "text": report.read_text("utf-8") if report.is_file() else "",
        }
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run", action="append", required=True, metavar="LABEL=DIRECTORY")
    parser.add_argument("--benchmark", type=Path, required=True, help="DRB revision directory")
    args = parser.parse_args()

    criteria = {
        row["id"]: row
        for row in map(json.loads, (args.benchmark / CRITERIA).read_text("utf-8").splitlines())
    }
    args.output.mkdir(parents=True, exist_ok=False)
    rubrics = args.output / "rubrics"
    rubrics.mkdir()
    documents = []
    for index, item in enumerate(args.run, start=1):
        label, _, directory = item.partition("=")
        for number, report in sorted(drb_reports(Path(directory)).items()):
            answer = f"Doc_{index:03d}"
            row = {
                "question": number,
                "answer": answer,
                "run": label,
                "status": report["status"],
                "characters": len(report["text"]),
            }
            documents.append(row)
            if not report["text"].strip():
                row["exported"] = False
                continue
            row["exported"] = True
            target = args.output / "reports" / f"Report{number}"
            target.mkdir(parents=True, exist_ok=True)
            document = Document()
            for line in report["text"].splitlines():
                document.add_paragraph(line)
            document.save(target / f"{answer}.docx")
            (rubrics / f"criteria{number}.json").write_text(
                json.dumps(criteria[number], ensure_ascii=False, indent=2), "utf-8"
            )
    (args.output / "documents.json").write_text(json.dumps(documents, indent=2), "utf-8")
    print(json.dumps(documents, indent=2))


if __name__ == "__main__":
    main()

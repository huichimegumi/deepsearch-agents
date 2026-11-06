"""Offline output/context audit of frozen E12 attempts; never changes a grade."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from time import monotonic

from app.research.grounded_sql import MetricRelations
from app.research.metric_selection import MetricSelection, execute_selection
from app.research.metrics import MetricRegistry
from app.research.query_plan import BoundValue, quote
from evals.diagnostics.compare_e12 import INPUTS, case_dir, catalog, validate
from evals.diagnostics.e8 import digest, read
from evals.diagnostics.score_e8 import equivalent, execute_sql
from evals.worker_supervisor import atomic_json

# Deliberately restricted evaluator diagnostic, not a general SQL rewriter. Only
# an entire outer SELECT projection consisting of two literal REPLACEs qualifies.
IDENT = r'(?:[A-Za-z_][\w]*|"(?:""|[^"])+")'
LITERAL = r"'(?:''|[^'])*'"
FORMAT = re.compile(
    rf"\s*REPLACE\s*\(\s*REPLACE\s*\(\s*(?P<column>{IDENT}(?:\.{IDENT})?)"
    rf"\s*,\s*(?P<a>{LITERAL})\s*,\s*(?P<b>{LITERAL})\s*\)"
    rf"\s*,\s*(?P<c>{LITERAL})\s*,\s*(?P<d>{LITERAL})\s*\)"
    rf"(?:\s+AS\s+{IDENT})?\s*",
    re.I,
)
TOKENS = re.compile(
    rf"{LITERAL}|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/|[A-Za-z_][\w]*|[()]",
    re.S,
)


def outer_name_format(query):
    """Locate the outer projection without matching REPLACE inside CTEs/filters."""
    depth, start = 0, None
    for token in TOKENS.finditer(query):
        word = token[0].upper()
        if word == "(":
            depth += 1
        elif word == ")":
            depth -= 1
        elif depth == 0 and word == "SELECT":
            start = token.end()
        elif depth == 0 and word == "FROM" and start is not None:
            match = FORMAT.fullmatch(query[start : token.start()])
            if not match:
                return None
            return start, token.start(), match
    return None


def raw_name_query(query):
    projection = outer_name_format(query)
    if projection is None:
        return None
    start, end, match = projection
    return query[:start] + " " + match["column"] + " " + query[end:]


def name_audit(database, reference_sql, actual):
    """Exact raw-name and source uniqueness signals, NEVER query/task correctness.

    Only the first candidate column is considered, with one row required. Extra
    cells containing the target cannot rescue a wrong projected name. Even a
    unique matching name can occur under wrong predicates, so this awards no pass.
    """
    raw = raw_name_query(reference_sql)
    if raw is None:
        return {"available": False, "reason": "unsupported_reference_projection"}
    columns, rows = execute_sql(database, raw)
    if len(columns) != 1 or len(rows) != 1 or not isinstance(rows[0][0], str):
        return {"available": False, "reason": "not_single_text_target"}
    target = rows[0][0]
    reads = set()
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        started = monotonic()
        conn.set_progress_handler(lambda: int(monotonic() - started > 5), 1000)

        def authorize(op, table, column, *rest):
            if op == sqlite3.SQLITE_READ and column:
                reads.add((table, column))
            return (
                sqlite3.SQLITE_OK
                if op
                in {
                    sqlite3.SQLITE_SELECT,
                    sqlite3.SQLITE_READ,
                    sqlite3.SQLITE_FUNCTION,
                    sqlite3.SQLITE_RECURSIVE,
                }
                else sqlite3.SQLITE_DENY
            )

        conn.set_authorizer(authorize)
        conn.execute(raw).fetchmany(2)
        conn.set_authorizer(None)
        # The diagnostic only supports a direct base-table name column. A CTE
        # alias or ambiguous origin is unavailable, never guessed from the answer.
        # SQLite's raw projection column label identifies the source column in
        # the supported form; aliases were removed with the format expression.
        origins = [(t, c) for t, c in reads if c.casefold() == columns[0].casefold()]
        if len(origins) != 1:
            return {"available": False, "reason": "ambiguous_source_name_column"}
        table, column = origins[0]
        names = conn.execute(f"SELECT {quote(column)} FROM {quote(table)} LIMIT 10001").fetchall()
    if len(names) > 10000:
        return {"available": False, "reason": "source_name_budget"}

    def normalize(s):
        return s.casefold().strip()

    count = sum(isinstance(n, str) and normalize(n) == normalize(target) for (n,) in names)
    candidate_rows = actual["rows"]
    same = (
        len(candidate_rows) == 1
        and bool(candidate_rows[0])
        and isinstance(candidate_rows[0][0], str)
        and normalize(candidate_rows[0][0]) == normalize(target)
    )
    return {
        "available": True,
        "first_column_raw_name_equal": same,
        "source_name_occurrences": count,
        "unique_source_name_equal": same and count == 1,
        "query_correctness_proven": False,
        "task_pass_credit": False,
    }


def context_audit(entries, payload, question, reference_sql):
    """Evaluator-only lexical coverage hints; token presence is not sufficiency."""
    selected = {e["id"] for e in payload["public_definitions"]}
    literals = {
        token[1:-1].replace("''", "'").casefold()
        for token in re.findall(LITERAL, reference_sql)
        if len(token[1:-1].strip()) >= 3
    }
    missing = set()
    for value in literals:
        if value in question.casefold():
            continue
        sources = {e["id"] for e in entries if value in str(e.get("definition", "")).casefold()}
        if sources and not sources & selected:
            missing.update(sources)
    result = {
        "public_definition_count": len(entries),
        "supplied_definition_count": len(selected),
        "omitted_literal_bearing_definition_ids": sorted(missing),
        "scope": "Lexical omission hints only; neither necessary-definition proof nor semantic coverage",
    }
    projection = outer_name_format(reference_sql)
    if projection:
        operands = [projection[2][key][1:-1].replace("''", "'").casefold() for key in ("a", "c")]
        meaningful = [value for value in operands if len(value.strip()) >= 3]
        public_text = question.casefold() + json.dumps(entries, ensure_ascii=False).casefold()
        result["reference_format_contract"] = {
            "nontrivial_source_operands": len(meaningful),
            "source_operands_found_in_public_text": sum(v in public_text for v in meaningful),
            "explicit_naming_instruction_cue": bool(
                re.search(r"normaliz|remov|replac|strip|formatt|omit|suffix", question, re.I)
            ),
            "scope": "Lexical evidence only; hidden reference transformations are not generator requirements",
        }
    return result


def audit(output, destination):
    manifest = read(output / "manifest.json")
    validate(output, manifest, backend_revision=True)
    destination.mkdir(parents=True, exist_ok=False)
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    refs = {r["id"]: r for r in read(INPUTS / "references.json")}
    cases = []
    for key in manifest["frozen"]["protocol"]["cases"]:
        path, task = case_dir(output, key), public[key]
        source = catalog(task)
        entries = [json.loads(line) for line in source.schema_notes.splitlines() if line.strip()]
        registry = MetricRegistry(source.sqlite_path, entries)
        payload = read(path / "input.json")
        values = {k: BoundValue.model_validate(v) for k, v in read(path / "values.json").items()}
        query = refs[key]["oracle"]["reference_sql"]
        expected = execute_sql(source.sqlite_path, query)
        relations = MetricRelations(registry, [d["table"] for d in payload["datasets"]])
        arms = []
        try:
            for route in manifest["frozen"]["protocol"]["routes"]:
                candidates = sorted(
                    (path / route).glob("candidate-*.json"),
                    key=lambda p: int(p.stem.split("-")[-1]),
                )
                candidate = candidates[-1]
                number = int(candidate.stem.split("-")[-1])
                saved = read(candidate)
                trace = read(path / route / "trace" / f"model-{number:03d}-response.json")
                if trace["parsed"] != saved:
                    raise ValueError("audit_candidate_trace_changed")
                row = {"route": route, "attempt": number, "candidate_sha256": digest(saved)}
                try:
                    if route == "selection":
                        records, _, parameters, _, _ = execute_selection(
                            registry, MetricSelection.model_validate(saved), values
                        )
                        actual = execute_sql(
                            source.sqlite_path, records[0]["metadata"]["query"], parameters
                        )
                    else:
                        actual = relations.execute(saved["sql"], values)
                    row.update(
                        status="executed",
                        row_count=len(actual[1]),
                        column_count=len(actual[0]),
                        strict_match=equivalent(expected, actual),
                        name_audit=name_audit(
                            source.sqlite_path, query, {"columns": actual[0], "rows": actual[1]}
                        ),
                    )
                except (ValueError, sqlite3.Error) as exc:
                    row.update(status="error", error_class=type(exc).__name__, strict_match=False)
                arms.append(row)
        finally:
            relations.close()
        cases.append(
            {
                "id": key,
                "reference_rows": len(expected[1]),
                "reference_columns": len(expected[0]),
                "context": context_audit(entries, payload, task["question"], query),
                "arms": arms,
            }
        )
    summary = {
        "scope": "Offline last-attempt audit, no new model scores or task pass credit",
        "api_calls": 0,
        "manifest_sha256": digest(manifest),
        "original_summary_sha256": digest(read(output / "summary.json")),
        "cases": cases,
    }
    atomic_json(destination / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.saved, args.output)
    print({"api_calls": 0, "cases": len(result["cases"])})

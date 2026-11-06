"""Bounded, field-scoped candidate values read from the actual allowed database."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from time import monotonic

from app.research.actions import sql_query
from app.research.query_plan import BoundValue, quote


@dataclass
class ValueCatalog:
    values: dict[str, BoundValue]
    evidence: list[dict]
    fields: list[dict]
    incomplete: bool

    def view(self):
        return {
            "fields": self.fields,
            "incomplete": self.incomplete,
            "scope": "Observed field values, not proof of entity identity or question relevance. Missing values may be outside this bounded preview.",
        }


def observe_values(registry, question, *, per_field=8, total=120, seconds=5, field_ids=None):
    if not 1 <= per_field <= 20 or not 1 <= total <= 200 or not 0 < seconds <= 20:
        raise ValueError("invalid_observation_budget")
    deadline = monotonic() + seconds
    values, evidence, fields, incomplete = {}, [], [], False
    terms = set(re.findall(r"[a-z]+", question.lower()))
    table_scores = {}
    for table in {ref.split(".")[0] for ref in registry.columns.values()}:
        table_scores[table] = max(
            (
                len(terms & set(re.findall(r"[a-z]+", entry.get("metric", ""))))
                for entry in registry.catalog(table)
            ),
            default=0,
        )
    ordered = sorted(
        (
            (key, ref)
            for key, ref in registry.columns.items()
            if field_ids is None or key in field_ids
        ),
        key=lambda item: (
            -table_scores[item[1].split(".")[0]],
            -len(terms & set(re.findall(r"[a-z]+", item[1].lower()))),
        ),
    )
    collected = []
    for field_id, ref in ordered[:64]:
        if monotonic() >= deadline:
            incomplete = True
            break
        table, column = ref.split(".")
        query = (
            f"SELECT DISTINCT {quote(column)} AS observed_value FROM {quote(table)} "
            f"WHERE typeof({quote(column)}) = 'text' "
            f"ORDER BY (length({quote(column)}) > 0 AND "
            f"instr(lower(:question), lower({quote(column)})) > 0) DESC, {quote(column)} "
            f"LIMIT {per_field + 1}"
        )
        try:
            records, notices = sql_query(
                registry.database,
                query,
                {"question": question},
                limit=per_field,
                seconds=max(0.01, deadline - monotonic()),
            )
        except sqlite3.OperationalError as exc:
            if "interrupted" not in str(exc):
                raise
            incomplete = True
            break
        records = [r for r in records if "observed_value" in r["content"]]
        if records:
            mentioned = any(
                r["content"]["observed_value"]
                and r["content"]["observed_value"].casefold() in question.casefold()
                for r in records
            )
            collected.append((table_scores[table], mentioned, not notices, field_id, ref, records))
    incomplete |= len(ordered) > 64
    collected.sort(key=lambda row: (-row[0], -row[1], -row[2]))
    for _, _, complete, field_id, ref, records in collected:
        if len(values) >= total:
            incomplete = True
            break
        shown = records[: total - len(values)]
        candidates = []
        for record in shown:
            content = record["content"]
            key = f"v{len(values) + 1}"
            values[key] = BoundValue(
                value=content["observed_value"], source_ref=record["evidence_id"], field_ref=ref
            )
            evidence.append(record)
            candidates.append({"key": key, "value": content["observed_value"]})
        complete = complete and len(shown) == len(records)
        fields.append({"field": field_id, "values": candidates, "complete": complete})
        incomplete |= not complete
    return ValueCatalog(values, evidence, fields, incomplete)

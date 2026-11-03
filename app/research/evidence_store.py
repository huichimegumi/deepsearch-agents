"""Complete durable evidence with replaceable, token-budgeted model views."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.research.sources import _tokens
from app.research.storage import write_json


def count_tokens(value):
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))
    except ImportError:
        return len(text.encode())


class EvidenceStore:
    def __init__(self, output: Path):
        self.directory = output / "evidence"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records = {}
        self.steps = {}
        self.annotations = {}
        self.selection_number = 0

    def add(self, records, step):
        for record in records:
            key = record["evidence_id"]
            if key in self.records and any(
                self.records[key].get(field) != record.get(field)
                for field in ("content", "source", "locator")
            ):
                raise ValueError("evidence_identity_collision")
            annotations = self.annotations.setdefault(key, [])
            metadata = record.get("metadata", {})
            if metadata not in annotations:
                annotations.append(metadata)
            if key not in self.records:
                write_json(
                    self.directory / (hashlib.sha256(key.encode()).hexdigest() + ".json"), record
                )
                self.records[key] = record
            self.steps.setdefault(key, set()).add(step)
        write_json(
            self.directory / "index.json",
            {
                "records": [
                    {
                        "id": key,
                        "file": hashlib.sha256(key.encode()).hexdigest() + ".json",
                        "source": r["source"],
                        "steps": sorted(self.steps[key]),
                        "metadata_versions": self.annotations[key],
                    }
                    for key, r in self.records.items()
                ]
            },
        )

    def select(self, question, *, max_tokens=12000):
        scope = "Exact source contents or explicitly marked excerpts; full records readable by ID."
        terms = _tokens(question)
        candidates = []
        for ordinal, (key, raw) in enumerate(self.records.items()):
            content = raw["content"]
            view = {"evidence_id": key, "source": raw["source"], "content": content}
            if raw["source"] != "sql":
                view["locator"] = raw["locator"]
            if isinstance(content, str) and len(content) > 6500:
                matches = [
                    m.start()
                    for word in terms
                    for m in re.finditer(re.escape(word), content.casefold())
                ]
                start = max(0, (min(matches) if matches else 0) - 1500)
                end = min(len(content), start + 6000)
                view["content"] = content[start:end]
                view["excerpt"] = {"start": start, "end": end, "full_record_available": True}
            query = (raw.get("metadata") or {}).get("query", "")
            words = _tokens(json.dumps(content, ensure_ascii=False) + " " + query)
            overlap = len(terms & words) / max(1, len(terms))
            # Later targeted results can displace earlier irrelevant bulk rows.
            score = (
                overlap * 8
                + (0.8 if raw["source"] == "sql" else 0)
                + ordinal / max(1, len(self.records)) * 0.15
            )
            candidates.append(
                (
                    score,
                    ordinal,
                    view,
                    {"sql": query, "parameters": (raw.get("metadata") or {}).get("parameters", {})}
                    if query
                    else None,
                )
            )
        candidates.sort(key=lambda item: (-item[0], -item[1]))
        chosen, queries, chosen_sources = [], {}, set()
        # Ensure a relevant source is not crowded out by another source's bulk rows.
        candidates.sort(key=lambda item: -item[0])
        reserved = []
        for source in sorted({row[2]["source"] for row in candidates}):
            reserved.append(next(row for row in candidates if row[2]["source"] == source))
        ordered = reserved + [row for row in candidates if row not in reserved]
        for score, ordinal, view, query in ordered:
            extra = dict(queries)
            if query:
                query_id = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[
                    :10
                ]
                extra[query_id] = query
                view = {**view, "query_id": query_id}
            if (
                count_tokens({"evidence": chosen + [view], "sql_queries": extra, "scope": scope})
                > max_tokens
            ):
                continue
            chosen.append(view)
            queries = extra
            chosen_sources.add(view["source"])
        payload = {
            "evidence": chosen,
            "sql_queries": queries,
            "scope": scope,
        }
        self.selection_number += 1
        write_json(
            self.directory / f"context-{self.selection_number:03d}.json",
            {
                **payload,
                "available_records": len(self.records),
                "selected_records": len(chosen),
                "estimated_tokens": count_tokens(payload),
                "token_limit": max_tokens,
            },
        )
        return payload

    def read(self, ids):
        if len(ids) > 8:
            raise ValueError("evidence_read_limit")
        return [self.records[key] for key in ids]

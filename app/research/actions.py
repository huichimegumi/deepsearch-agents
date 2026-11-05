"""Typed source actions and parameterized, read-only SQLite execution."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Literal

from pydantic import BaseModel, Field

from app.research.evidence.adapters import sql_rows_to_evidence
from app.research.evidence.models import EvidenceRecord, EvidenceSource


class Parameter(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$", max_length=50)
    value: str | int | float | bool | None = None
    evidence_id: str | None = None
    path: list[str | int] = Field(default_factory=list, max_length=8)


class Action(BaseModel):
    source: Literal["sql", "web", "local_document", "fee_engine"]
    operation: Literal[
        "query", "sample_table", "match_column_value", "search_semantics", "read_evidence"
    ] = "query"
    query: str = Field(default="", max_length=6000)
    parameters: list[Parameter] = Field(default_factory=list, max_length=16)
    table: str = ""
    column: str = ""
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    depends_on: list[str] = Field(default_factory=list, max_length=5)


class Decision(BaseModel):
    reason: str
    action: Action | None = None


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def bind(action, store):
    values, bindings, parents = {}, [], set(action.depends_on)
    for parameter in action.parameters:
        if parameter.name in values:
            raise ValueError("duplicate_parameter")
        value = parameter.value
        if parameter.evidence_id:
            record = store.records[parameter.evidence_id]
            content = record["content"]
            if parameter.path:
                for key in parameter.path:
                    content = content[key]
                if isinstance(content, (dict, list)):
                    raise ValueError("parameter_requires_scalar_path")
                value = content
            elif normalize(value) not in normalize(json.dumps(content, ensure_ascii=False)):
                raise ValueError("parameter_not_supported_by_evidence")
            parents.update(store.steps[parameter.evidence_id])
            bindings.append(
                {
                    "name": parameter.name,
                    "value": value,
                    "evidence_id": parameter.evidence_id,
                    "path": parameter.path,
                }
            )
        values[parameter.name] = value
    return values, bindings, sorted(parents)


@lru_cache(maxsize=32)
def fingerprint(path, size, mtime):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def named_parameters(query):
    # Colons in string literals, quoted identifiers or comments are not bindings.
    lexical = re.sub(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`|\[[^\]]*\]|--[^\n]*|/\*.*?\*/",
        " ",
        query,
        flags=re.S,
    )
    return set(re.findall(r"(?<!:):([a-zA-Z][a-zA-Z0-9_]*)", lexical))


def sql_query(database, query, parameters, *, seconds=20, limit=80):
    required = named_parameters(query)
    if required != set(parameters):
        raise ValueError("sql_parameter_names_mismatch")
    database = database.resolve()
    stat = database.stat()
    identity = fingerprint(str(database), stat.st_size, stat.st_mtime_ns)
    parameter_hash = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    started = monotonic()
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        conn.set_authorizer(
            lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        )
        conn.set_progress_handler(lambda: int(monotonic() - started > seconds), 10000)
        cursor = conn.execute(query, parameters)
        if cursor.description is None:
            raise ValueError("query_requires_tabular_result")
        columns = [c[0] for c in cursor.description]
        if len({column.casefold() for column in columns}) != len(columns):
            raise ValueError("duplicate_query_output_columns")
        rows = cursor.fetchmany(limit + 1)
    records = [
        r.to_dict()
        for r in sql_rows_to_evidence(
            query=query,
            columns=columns,
            rows=rows[:limit],
            database_identity=f"{identity}/parameters/{parameter_hash}",
        )
    ]
    if not rows:
        records = [
            EvidenceRecord.create(
                source=EvidenceSource.SQL,
                locator=f"sql://{identity}/empty/{hashlib.sha256((query + parameter_hash).encode()).hexdigest()}",
                content={"row_count": 0, "columns": columns, "rows": []},
                identity={"parameters_sha256": parameter_hash},
                metadata={
                    "query": query,
                    "parameters": parameters,
                    "evidence_kind": "empty_query_result",
                },
            ).to_dict()
        ]
    for record in records:
        record["metadata"].update(
            parameters=parameters, returned_rows=min(len(rows), limit), truncated=len(rows) > limit
        )
    return records, (
        ["SQL preview truncated; aggregate or narrow the query."] if len(rows) > limit else []
    )


def describe(catalog, question):
    raw = catalog.describe()
    result = {
        "allowed_sources": catalog.allowed_sources,
        "operations": {
            "sql": [
                "query (named :parameters)",
                "sample_table",
                "match_column_value",
                "search_semantics",
            ],
            "web": ["query with {{parameter}} placeholders"],
            "local_document": ["query"],
            "all": ["read_evidence (up to eight IDs)"],
        },
    }
    meanings = {}
    if catalog.sqlite_path:
        result["sql_dialect"] = "sqlite"
        stem = catalog.sqlite_path.stem.removesuffix("_template")
        path = catalog.sqlite_path.with_name(stem + "_column_meaning_base.json")
        if path.is_file() and path.stat().st_size < 2_000_000:
            for key, value in json.loads(path.read_text(encoding="utf-8")).items():
                parts = key.split("|")
                if len(parts) == 3:
                    meanings[(parts[1], parts[2])] = value
            result["column_metadata_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    tables = []
    for record in raw.get("sql_schema", []):
        content = record["content"]
        tables.append(
            {
                "table": content["table_name"],
                "foreign_keys": content.get("foreign_keys", []),
                "unique_keys": [
                    index.get("columns", [])
                    for index in content.get("indexes", [])
                    if index.get("unique")
                ],
                "columns": [
                    {
                        "name": c["name"],
                        "type": c.get("declared_type", ""),
                        "primary_key_position": c.get("primary_key_position", 0),
                        "nullable": not c.get("not_null", False),
                        "meaning": meanings.get(
                            (content["table_name"], c["name"]), c.get("semantic_description", "")
                        ),
                    }
                    for c in content["columns"]
                ],
            }
        )
    if tables:
        result["sql_tables"] = tables
    if catalog.schema_notes:
        from app.research.sources import _tokens

        entries = [json.loads(line) for line in catalog.schema_notes.splitlines() if line.strip()]
        terms = _tokens(question)
        ranked = sorted(entries, key=lambda row: -len(terms & _tokens(json.dumps(row))))
        result["semantic_definitions"] = ranked[:5]
    for source in ("web", "local_document"):
        if source in raw:
            result[source] = raw[source]
    return result


def collect(catalog, action, store):
    if action.source not in catalog.allowed_sources:
        raise ValueError("source_not_allowed")
    values, bindings, parents = bind(action, store)
    if action.operation == "read_evidence":
        return store.read(action.evidence_ids), [], bindings, parents, action.query
    if action.source == "sql":
        if catalog.sqlite_path is None:
            raise ValueError("typed_sql_requires_sqlite_catalog")
        if action.operation == "query":
            records, notices = sql_query(catalog.sqlite_path, action.query, values)
            return records, notices, bindings, parents, action.query
        if action.operation in {"sample_table", "match_column_value"}:
            from app.tools.evidence_tool import _collect_sqlite

            query = action.query
            for name, value in values.items():
                query = query.replace("{{" + name + "}}", str(value))
            batch = _collect_sqlite(
                query,
                action.operation,
                catalog.sqlite_path,
                table_name=action.table,
                column_name=action.column,
            )
            if batch.status.value == "ERROR":
                raise ValueError("; ".join(batch.warnings))
            return (
                [r.to_dict() for r in batch.records],
                list(batch.warnings),
                bindings,
                parents,
                query,
            )
        if action.operation == "search_semantics":
            from app.research.sources import _tokens

            entries = [
                json.loads(line) for line in catalog.schema_notes.splitlines() if line.strip()
            ]
            ranked = sorted(
                entries, key=lambda row: -len(_tokens(action.query) & _tokens(json.dumps(row)))
            )[:3]
            records = [
                EvidenceRecord.create(
                    source=EvidenceSource.SQL,
                    locator="schema:knowledge:"
                    + hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(),
                    content=row,
                    metadata={"evidence_kind": "database_semantics"},
                ).to_dict()
                for row in ranked
            ]
            return records, [], bindings, parents, action.query
    if action.operation != "query":
        raise ValueError("invalid_source_operation")
    query = action.query
    for name, value in values.items():
        if "{{" + name + "}}" not in query:
            raise ValueError("unused_source_parameter")
        query = query.replace("{{" + name + "}}", str(value))
    records, notices = catalog.collect(action.source, query)
    return records, notices, bindings, parents, query

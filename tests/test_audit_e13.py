import sqlite3

from evals.diagnostics.audit_e13 import context_audit, name_audit, raw_name_query
from evals.diagnostics.score_e8 import equivalent


def database(tmp_path):
    db = tmp_path / "names.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE objects(id INTEGER PRIMARY KEY, name TEXT, score REAL); INSERT INTO objects VALUES (1,'Alpha Site',1),(2,'Beta Site',2),(3,'AlphaSite',3);"
        )
    return db


REFERENCE = "WITH ranked AS (SELECT name,score FROM objects) SELECT REPLACE(REPLACE(name,' ',''),'-','') AS answer FROM ranked ORDER BY score LIMIT 1"


def test_name_diagnostic_does_not_award_task_credit_or_change_strict_grade(tmp_path):
    db = database(tmp_path)
    actual = {"columns": ["name", "score"], "rows": [("Alpha Site", 1)]}
    result = name_audit(db, REFERENCE, actual)
    assert result["unique_source_name_equal"]
    assert not result["task_pass_credit"] and not result["query_correctness_proven"]
    assert not equivalent((["answer"], [("AlphaSite",)]), (actual["columns"], actual["rows"]))
    # The wrong entity has the same formatted name. Never strip names globally.
    assert not name_audit(db, REFERENCE, {"rows": [("AlphaSite",)]})["first_column_raw_name_equal"]
    for rows in [
        [("Beta Site", "Alpha Site")],
        [("Alpha", "Site")],
        [("Alpha Site",), ("Beta Site",)],
        [],
    ]:
        assert not name_audit(db, REFERENCE, {"rows": rows})["first_column_raw_name_equal"]
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO objects VALUES(4,'Alpha Site',4)")
    result = name_audit(db, REFERENCE, actual)
    assert result["first_column_raw_name_equal"] and not result["unique_source_name_equal"]
    assert result["source_name_occurrences"] == 2


def test_only_whole_outer_projection_can_be_deformatted():
    assert raw_name_query(REFERENCE).endswith("SELECT name FROM ranked ORDER BY score LIMIT 1")
    for query in [
        "WITH x AS (SELECT REPLACE(REPLACE(name,' ',''),'-','') FROM objects) SELECT name FROM objects",
        "SELECT name FROM objects WHERE REPLACE(REPLACE(name,' ',''),'-','')='x'",
        "SELECT REPLACE(REPLACE(name,' ',''),'-',''),score FROM objects",
        "SELECT 'SELECT REPLACE(REPLACE(name, space, empty), dash, empty) FROM objects' FROM objects",
    ]:
        assert raw_name_query(query) is None


def test_context_audit_reports_lexical_omissions_without_disclosing_values():
    entries = [
        {"id": 1, "definition": "Category Copper"},
        {"id": 2, "definition": "Category Silver"},
    ]
    audit = context_audit(
        entries,
        {"public_definitions": entries[:1]},
        "Choose category",
        "SELECT name FROM x WHERE category='Silver'",
    )
    assert audit["omitted_literal_bearing_definition_ids"] == [2]
    assert "Silver" not in str(audit)
    assert (
        context_audit(
            entries,
            {"public_definitions": entries[:1]},
            "Choose Silver",
            "SELECT name FROM x WHERE category='Silver'",
        )["omitted_literal_bearing_definition_ids"]
        == []
    )


def test_reference_only_name_transforms_are_not_public_requirements():
    audit = context_audit([], {"public_definitions": []}, "Find the name", REFERENCE)
    # Space and punctuation operands are too short to establish a public rule.
    assert audit["reference_format_contract"]["nontrivial_source_operands"] == 0
    query = REFERENCE.replace("' '", "' Observatory'")
    audit = context_audit([], {"public_definitions": []}, "Find the name", query)
    contract = audit["reference_format_contract"]
    assert contract["nontrivial_source_operands"] == 1
    assert contract["source_operands_found_in_public_text"] == 0
    assert not contract["explicit_naming_instruction_cue"]
    assert "Observatory" not in str(audit)

import json
from collections import Counter
from pathlib import Path

from evals.standards.prepare import LOCK, SPLITS


def test_development_and_holdout_have_disjoint_sources_and_hidden_labels():
    source_sets = [{rfc for ids in groups.values() for rfc in ids} for groups in SPLITS.values()]
    assert not source_sets[0] & source_sets[1]
    root = Path(LOCK).parent
    for split, expected_count in (("dev", 16), ("holdout", 24)):
        cases = json.loads((root / f"{split}.json").read_text())
        public = json.loads((root / f"{split}.public.json").read_text())
        assert len(cases) == expected_count
        assert set(Counter(row["category"] for row in cases).values()) == {expected_count // 4}
        assert [
            {key: row[key] for key in ("id", "question", "sources", "split")} for row in cases
        ] == public
        assert all("oracle" not in row for row in public)
        assert sum(not row["oracle"]["answerable"] for row in cases) == 2
        assert all(
            row["oracle"].get("require_sql_web_dependency")
            for row in cases
            if row["category"] == "mixed"
        )

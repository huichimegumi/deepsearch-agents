"""DRB-only OSODT parser compatibility for unambiguous single-dimension arrays."""

import json
from math import isfinite

from aeollm2_osodt.parsing import _extract_payload_text
from aeollm2_osodt.parsing import parse_score_object as strict_parse

REVISION = "drb-single-dimension-array-v1"


def parse_score_object(raw, expected_counts, *, allow_comments=False):
    try:
        return strict_parse(raw, expected_counts, allow_comments=allow_comments)
    except ValueError as original:
        if len(expected_counts) != 1 or not isinstance(raw, str):
            raise
        try:
            payload = raw.strip()
            values = json.loads(payload if payload.startswith("[") else _extract_payload_text(raw))
        except ValueError:
            raise original from None
        dimension, count = next(iter(expected_counts.items()))
        if (
            not isinstance(values, list)
            or len(values) != count
            or not all(
                type(value) in (int, float) and 0 <= value <= 10 and isfinite(value)
                for value in values
            )
        ):
            raise original
        return strict_parse(json.dumps({dimension: values}), expected_counts)


def main():
    from aeollm2_osodt import pipeline
    from aeollm2_osodt.cli import main as judge_main

    pipeline.parse_score_object = parse_score_object
    judge_main()


if __name__ == "__main__":
    main()

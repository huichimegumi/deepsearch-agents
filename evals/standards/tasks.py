"""Original internal questions and hidden references over locked public standards."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from evals.standards.prepare import DATA, SPLITS

HERE = Path(__file__).parent


def _task(case_id, question, sources, checklist, reference, *, answerable=True, facts=None):
    return {
        "id": case_id,
        "question": question,
        "sources": sources,
        "required_sources": sources,
        "oracle": {
            "answerable": answerable,
            "checklist": checklist,
            "reference": reference,
            "facts": facts or [],
        },
    }


def build(split: str) -> Iterator[dict]:
    rows = []
    for role, ids in SPLITS[split].items():
        for rfc in ids:
            raw = json.loads((DATA / f"rfc{rfc}.json").read_text())
            rows.append(
                {
                    "rfc": rfc,
                    "year": int(raw["pub_date"].split()[-1]),
                    "page_count": int(raw["page_count"]),
                    "role": role,
                    "authors": raw["authors"],
                }
            )
    # Independent reference reductions over source JSON; executor queries imported SQL.
    definitions = [
        ("document_count", "Count all standards rows", len(rows)),
        (
            "earliest_year",
            "Find the earliest publication year in standards",
            min(row["year"] for row in rows),
        ),
        (
            "web_document_count",
            "Count standards rows whose source_role is web",
            sum(row["role"] == "web" for row in rows),
        ),
        (
            "distinct_author_count",
            "Count distinct author names across all rows of authors",
            len({author for row in rows for author in row["authors"]}),
        ),
    ]
    if split == "holdout":
        definitions += [
            (
                "total_pages",
                "Sum page_count across all rows in standards",
                sum(row["page_count"] for row in rows),
            ),
            (
                "latest_rfc",
                "Find the largest RFC identifier among standards rows with year >= 2014",
                max(row["rfc"] for row in rows if row["year"] >= 2014),
            ),
        ]
    for index, (metric, request, expected) in enumerate(definitions):
        rows_task = _task(
            f"{split}_sql_{index}",
            f"Use only the SQL database. {request}. Return the exact numeric metric {metric} with a source-field binding.",
            ["sql"],
            [f"Report the independently correct {metric} and cite the executed SQL result"],
            "SQL reference is independently reduced from the publisher JSON snapshot.",
            facts=[{"metric": metric, "value": str(expected)}],
        )
        rows_task["category"] = "sql"
        rows_task["split"] = split
        yield rows_task
    if split == "dev":
        local = [
            (
                "According to local RFC 8446, how does TLS 1.3 treat static RSA key exchange?",
                [
                    "Explain that static RSA key exchange is removed from TLS 1.3",
                    "Ground the statement in retrieved local RFC text",
                ],
                "TLS 1.3 removes static RSA and static Diffie-Hellman cipher suites; RSA signatures are a separate issue.",
                True,
            ),
            (
                "Compare local RFC 4627 and RFC 8259 on which values may be a complete JSON text. Explain the apparent version conflict.",
                [
                    "Distinguish older object/array restriction from later serialized value",
                    "Attribute each rule to its RFC/version with both sources",
                ],
                "RFC 4627 restricts JSON text to object or array; RFC 8259 permits a serialized value, including scalars.",
                True,
            ),
            (
                "Using only local RFC 8259, report the exact maximum number of object members all JSON parsers must accept. Refuse a universal numeric limit if none is specified.",
                [
                    "State that the supplied standard does not fix a universal numeric object-member limit",
                    "Avoid inventing a number and state the evidence scope",
                ],
                "Implementations may impose limits; no universal required member-count maximum is specified.",
                False,
            ),
            (
                "Using only local RFC 9111, what fixed retention period in days must every HTTP cache apply? Refuse a universal number if it is not specified.",
                [
                    "Explain that no single mandatory retention-day count applies to all caches",
                    "Do not fabricate a period; scope the refusal to the supplied standard",
                ],
                "Freshness and cache directives vary; there is no universal fixed retention period.",
                False,
            ),
        ]
        web = [
            (
                9309,
                "How are equally specific allow and disallow rules resolved in the Robots Exclusion Protocol?",
                [
                    "Explain most-specific matching",
                    "When allow/disallow rules are equivalent, allow SHOULD be used",
                ],
                "RFC 9309 chooses the most specific octet match; equivalent allow/disallow prefers allow with SHOULD strength.",
            ),
            (
                3986,
                "Compare the classification of parentheses in RFC 2396 and RFC 3986. Explain the version difference using both sources.",
                [
                    "RFC 2396 includes parentheses among unreserved marks",
                    "RFC 3986 classifies parentheses as reserved sub-delimiters",
                    "Attribute the differing rules to the correct versions",
                ],
                "RFC 2396 unreserved mark includes parentheses; RFC 3986 moves them into reserved sub-delims.",
            ),
            (
                6265,
                "Distinguish the Secure and HttpOnly cookie attributes and their limitations.",
                [
                    "Secure restricts transmission to secure channels",
                    "HttpOnly restricts access through non-HTTP APIs",
                    "Do not claim Secure alone prevents all integrity attacks",
                ],
                "Secure constrains transport; HttpOnly constrains scripting access; neither is a complete integrity guarantee.",
            ),
            (
                6455,
                "What does WebSocket close status 1000 mean, and how does it differ from 1001?",
                ["1000 is normal completion", "1001 means an endpoint is going away"],
                "RFC 6455 defines normal closure 1000 and going-away 1001.",
            ),
        ]
    else:
        local = [
            (
                "Using local RFC 6901, explain the encodings of slash and tilde in JSON Pointer reference tokens and their decoding order.",
                [
                    "Slash uses ~1 and tilde uses ~0",
                    "Decode ~1 before ~0 to avoid mis-decoding ~01",
                ],
                "JSON Pointer token decoding applies ~1 to slash then ~0 to tilde.",
                True,
            ),
            (
                "Using local RFC 7396, explain null members in JSON Merge Patch and what a non-object patch does to its target.",
                [
                    "Null object members remove target members",
                    "A non-object patch replaces the entire target",
                    "Mention arrays are not patched element by element",
                ],
                "Merge Patch null members delete; non-object patch replaces the target as a whole.",
                True,
            ),
            (
                "Using local RFC 6585, explain 429 and whether Retry-After is mandatory. Distinguish normative strength.",
                [
                    "429 means too many requests/rate limiting",
                    "Retry-After MAY be supplied, not mandatory",
                ],
                "RFC 6585 429 response MAY include Retry-After.",
                True,
            ),
            (
                "Using local RFC 3339, compare -00:00 with Z or +00:00; explain why treating them as identical loses information.",
                [
                    "-00:00 means UTC time known but local offset unknown",
                    "Z/+00:00 implies UTC is the preferred reference",
                ],
                "RFC 3339 distinguishes unknown local offset from a preferred UTC reference.",
                True,
            ),
            (
                "Only local RFC 8288 is available: what is the exact number of Link header fields allowed by our deployed reverse proxy? Refuse if deployment-specific evidence is absent.",
                [
                    "Refuse the deployment-specific numeric count",
                    "Distinguish protocol specification from actual proxy configuration",
                ],
                "The supplied RFC does not describe this deployment or its header-count setting.",
                False,
            ),
            (
                "Using local RFC 9112, give our production service's measured request-smuggling incident count last month. Refuse if telemetry is absent.",
                [
                    "Refuse to fabricate an incident count",
                    "Explain that protocol security guidance is not production telemetry",
                ],
                "No production incident telemetry is present in the local standards snapshot.",
                False,
            ),
        ]
        web = [
            (
                5861,
                "Compare stale-while-revalidate and stale-if-error: what different conditions allow stale responses?",
                [
                    "stale-while-revalidate permits serving stale while revalidating in the background",
                    "stale-if-error permits stale content on qualifying failures",
                    "Respect their bounded time windows",
                ],
                "RFC 5861 defines separate stale revalidation and error controls with delta-second bounds.",
            ),
            (
                6797,
                "Explain HSTS includeSubDomains and what happens if max-age is zero.",
                [
                    "includeSubDomains extends HSTS policy to subdomains",
                    "max-age=0 removes the host's stored HSTS policy",
                ],
                "includeSubDomains covers descendant hosts; max-age zero removes the known host's policy, not necessarily an inherited parent policy.",
            ),
            (
                7617,
                "Does HTTP Basic authentication encrypt credentials? Explain its Base64 encoding and transport requirement.",
                [
                    "Base64 is encoding, not encryption",
                    "Credentials need an external secure transport such as TLS for confidentiality",
                ],
                "Basic credentials are readily decoded without external encryption; TLS protects transport.",
            ),
            (
                7239,
                "Explain why Forwarded values cannot automatically be trusted and how privacy can be improved.",
                [
                    "The field may be modified or supplied by untrusted intermediaries",
                    "Obfuscated identifiers and minimized disclosure mitigate privacy exposure",
                ],
                "Forwarded is not self-authenticating; trust depends on proxy boundaries; use privacy protections.",
            ),
            (
                6266,
                "When Content-Disposition has filename and filename*, which should recipients prefer, and what filesystem precaution is required?",
                [
                    "Prefer filename* when both are understood",
                    "Treat filenames as advisory and strip path segments",
                ],
                "Recipients SHOULD prefer filename* and ignore filename; local storage must not trust supplied path components.",
            ),
            (
                9421,
                "Distinguish Signature-Input from Signature in HTTP Message Signatures and explain why selecting covered components matters.",
                [
                    "Signature-Input identifies covered components and signature parameters",
                    "Signature carries signature values",
                    "Only covered components are integrity protected by that signature",
                ],
                "RFC 9421 separates input metadata from signature values; coverage selection controls protected message semantics.",
            ),
        ]
    for index, (question, checklist, reference, answerable) in enumerate(local):
        task = _task(
            f"{split}_local_{index}",
            question,
            ["local_document"],
            checklist,
            reference,
            answerable=answerable,
        )
        task.update(category="local_document", split=split)
        yield task
    for index, (rfc, question, checklist, reference) in enumerate(web):
        task = _task(
            f"{split}_web_{index}",
            f"Use only the available Web snapshots, especially RFC {rfc}. {question}",
            ["web"],
            checklist,
            reference,
        )
        task.update(category="web", split=split)
        yield task
        metadata = json.loads((DATA / f"rfc{rfc}.json").read_text())
        mixed = _task(
            f"{split}_mixed_{index}",
            f"First use SQL to identify the RFC number and publication year for the standard titled {metadata['title']!r}. Return the exact numeric metric publication_year, citing the SQL result. Then use that identifier to query the available Web snapshots and answer: {question}",
            ["sql", "web"],
            ["Identify publication year using SQL evidence", *checklist],
            reference,
            facts=[{"metric": "publication_year", "value": metadata["pub_date"].split()[-1]}],
        )
        mixed.update(category="mixed", split=split)
        mixed["oracle"]["require_sql_web_dependency"] = True
        yield mixed


def main() -> None:
    for split in SPLITS:
        cases = sorted(build(split), key=lambda row: row["id"])
        (HERE / f"{split}.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
        public = [
            {key: row[key] for key in ("id", "question", "sources", "split")} for row in cases
        ]
        (HERE / f"{split}.public.json").write_text(
            json.dumps(public, ensure_ascii=False, indent=2) + "\n"
        )
        print(split, len(cases))


if __name__ == "__main__":
    main()

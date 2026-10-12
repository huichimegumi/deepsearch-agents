# M3.19 Multi-clue entity and SQL value grounding

## Post-M3.18 live validation

The post-M3.18 single-task run used the explicitly authorized Tavily 6/6 ceiling and consumed six
queries and six fetched pages. It produced six Web Evidence records, four accepted Claims, no
rejected Claims, and a citation-valid delivered fallback. Semantic retrieval also stayed compact at
the expected parent formula plus two dependencies.

Analytical SQL remained the only failed requirement. Both Supervisor queries completed without a
database error but returned no rows, and structured correction then exhausted its 60-second model
window before proposing a query. Audit inspection showed that the queries used a location mentioned
by one clue as the final entity. The remaining clues did not jointly support that choice. The
database also stores entity keys in a namespaced, fixed-width representation, so copying an
unverified Web label directly into an equality filter is unsafe.

No decrypted task, answer, reference SQL, model output, or local evaluation log is committed.

## Multi-clue convergence

The Web researcher now has an explicit entity-resolution rule for clue puzzles:

1. identify the named subject in each clue;
2. form and test the intersection of candidate entities;
3. treat a location supported by only one clue as a candidate, not the answer;
4. return unresolved candidates and evidence gaps instead of guessing when any clue remains
   unverified.

This is a general research constraint rather than benchmark-specific task knowledge.

## Bounded database value matching

SQLite Evidence adds `operation=match_column_value`. The caller supplies an exact catalog
`table_name`, exact `column_name`, and a human-readable entity label in `query`. The backend:

- validates the table and column against the read-only SQLite catalog before constructing SQL;
- binds the human label as a parameter and never interpolates it as an identifier or expression;
- scans at most 200 lexical candidates and returns at most eight deterministically ranked matches;
- distinguishes exact, prefix, suffix, and token-phrase matches;
- returns stable `database_value_match` Evidence with the requested label, physical location,
  matched value, and comparison mode;
- reports zero matches as `NO_EVIDENCE` and multiple matches as `PARTIAL`, requiring further
  resolution before analytical SQL.

Fixed-width text fields are normalized deliberately. `matched_value` omits storage padding, while
`comparison_mode=trimmed_text` tells the query planner to use `TRIM(column)=matched_value`.
Unpadded values use `comparison_mode=exact_text`.

These records are discovery-only. They are excluded from Claim validation just like schema,
samples, and formula definitions, but they remain available to SQL correction so the eventual
`query_result` can use a verified filter.

## Workflow contract

For a SQL filter derived from a Web or user-provided text entity, Supervisor research must call
`match_column_value` after schema discovery and before analytical SQL. A unique result authorizes
the exact filter value. Zero results require renewed entity resolution; multiple results require
disambiguation. SQL correction receives any value-match record beside the compact semantic formula
bundle and must honor its comparison mode.

The operation does not increase the Web-query, fetched-page, research-round, analytical SQL repair,
or correction-model budgets.

## Verification

Automated tests cover stable value-match IDs, suffix resolution, zero-match behavior, malicious
column rejection, discovery-only Claim gating, and correction-ledger preservation. A no-network
check against the locked database resolved the intended human label to one physical observatory key
and correctly detected its fixed-width padding as `trimmed_text`.

This stage intentionally performs no second Tavily run. The next live evaluation should verify the
complete sequence: all-clue Web convergence, a unique database value match, analytical SQL Evidence,
and strict reference-result equality.

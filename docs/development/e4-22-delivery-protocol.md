# E4.22 — Delivery requirements over the frozen ten-report baseline

E4.20 reported three `completed` executions, but E4.21 found that one of
them, `report_cross_002`, collected only SQL Evidence while claiming two
invented local-document citations. This stage adds a separate, explicit
delivery protocol check to the offline ten-case reviewer. It replays the
unchanged saved reports and source snapshots. There are no new Agent,
retrieval, model, or Tavily calls.

The check requires a nonempty report, completed execution, Evidence for
answerable tasks, and the required sources collected and cited where the
frozen suite specifies them. It rescans the actual delivered report using
the corrected versioned citation validator against saved Evidence IDs.
For local tasks, it also checks the existing local-source scope flag. A
no-answer task still needs separate semantic abstention review.

The [content-free replay](../../evals/reports/e4-22-delivery-protocol-2026-10-30.json)
uses private run `ten_case_review_20261030T083833Z_74cfa7db25` and retains
all ten tasks. `delivery_protocol_ready` is true for local 001 and local 004;
the other eight each have explicit reasons. The reason counts overlap:

| Reason | Tasks |
| --- | ---: |
| Execution not completed | 7 |
| Required source not collected | 1 |
| Required source not cited | 2 |
| Unknown citation | 1 |
| Missing citation in answerable report | 2 |

The historical SQL-plus-document task is now correctly marked not ready:
`required_source_not_collected`, `required_source_not_cited`, and
`unknown_citation`. The two ready tasks are **candidates for semantic
review**, not correct answers or an acceptance rate. In particular, local
004 lacks one finite reference unit despite its valid delivery protocol,
which is why retrieval/keypoint review remains separate.

The result points to two next tasks. First, review the two ready reports
against their source passages and answer keypoints, including local 004's
missing future-policy point. Second, investigate the five finite retrieval
gaps and seven degraded executions before choosing a runtime intervention.
The current stage changes evaluation classification only; production report
behavior and the E4.20 execution record are unchanged.

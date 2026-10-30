# E4.24 — Explicit source requirements at report delivery

The E4.20 SQL-plus-local task was marked `completed` despite collecting only
SQL Evidence, then writing invented local-document citations. E4.21 fixed the
versioned citation scanner, and E4.22 classified the saved output as not
ready. This stage adds an explicit caller-supplied source requirement to the
real report delivery path. The ordinary API and local-only report caller do
not set it. The frozen extended evaluator passes each task's existing
`required_sources` array to `run_deep_agent`.

After normal citation and Claim fallback checks, the backend compares each
required source against claim-eligible collected Evidence and against
Evidence IDs actually cited in the delivered candidate. If either check
fails, it withholds the answer, records `required_evidence_source_missing`,
marks the run degraded, and returns a bounded technical notice. SQL schema
descriptions and samples cannot satisfy an analytical SQL source requirement
because they are not claim-eligible. The check does not decide whether a
cited passage semantically supports the claim.

Focused tests cover missing local Evidence despite SQL, local Evidence that
was collected but not cited, a correctly cited SQL-plus-local pair, and
forwarding of the explicit caller contract. Default callers pass no source
requirement and retain their existing behavior.

## Live probe and limit

One real `report_cross_002` probe used the unchanged frozen asset lock and
per-task zero Web budget. The task admitted **zero Tavily queries** and kept
its inputs unchanged. Its upstream model timed out during research; the
subsequent cancellation took longer than the configured 330-second outer
watchdog. The final row is `cancelled`, with `TimeoutError`, `upstream_timeout`,
`cancelled`, and `cancelled_by_user_or_eval`; elapsed time is **1565.594
seconds**. The final report delivery branch was never reached, so this probe
does not demonstrate the new source gate in a live completed run. The
[content-free record](../../evals/reports/e4-24-required-source-delivery-2026-10-30.json)
preserves the old completed-but-missing-source case and this failed probe
without claiming answer improvement.

The unusually slow cancellation is a separate runtime boundary issue. Next
inspect the synchronous retrieval/model worker and cancellation path before
another lengthy live rerun. The remaining ten-case semantic accuracy is still
pending; this source gate prevents one known class of unsupported delivery
when it is reached, but does not repair missing retrieval or exhausted time.

# M2.2 Web Evidence

M2.2 promotes successfully fetched public pages into the same Evidence-to-Claim chain used by Fee
Engine, SQL, and local documents. Search discovery remains separate from evidence admission.

## Admission boundary

`research_search` now has two outputs with different trust levels:

- `results`: ranked discovery candidates. Each item is marked `FETCHED` or `CANDIDATE_ONLY`;
- `evidence_records`: full `EvidenceRecord` objects created only when public-page fetch and text
  parsing succeeded.

A provider snippet, title, URL, or generated provider answer is not Web Evidence. The network
researcher must request `fetch_full_page=true` before using a page in a report claim. Failed fetches
remain candidate-only gaps and receive no `evidence_id`.

Full-page fetching keeps the existing public-address check and now disables automatic redirects.
Each redirect target is resolved and checked again before the next request, so a public URL cannot
promote a redirect to a loopback or private-network resource into Evidence.

## Stable identity

Accepted pages use source `web` and IDs shaped as `ev1_web_<digest>`. Before hashing, the adapter:

1. lowercases URL scheme and host;
2. removes fragments and common tracking parameters;
3. normalizes insignificant whitespace in parsed page text;
4. excludes ranking score, matched query, backend, title, and publication metadata from identity.

The same canonical URL and normalized page text therefore keep the same ID across reranking,
provider changes, tracking links, and query wording. A substantive page-content change produces a
new ID. Metadata remains available for source inspection without destabilizing identity.

## Workflow integration

The tool records accepted Web Evidence in the current `ResearchRunTrace`. Compression can then use
those IDs in `ClaimDraft.evidence_ids`, and the M2.1 backend validates them exactly like internal
evidence. The final writer may cite accepted `[ev1_web_...]` values; unknown or candidate-only IDs
still fail the deterministic citation gate.

Fetched text appears once in the tool response, under `evidence_records`. Candidate rows retain
their snippets and status but omit duplicated raw page text, keeping the model context bounded.
Audit and trace events store IDs, locators, counts, and source categories rather than duplicating
page contents.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web_evidence.py `
  tests/test_search_service.py tests/test_claim_validation.py -q
```

Coverage includes URL and whitespace normalization, content changes, snippet rejection, tool
response and trace registration, and the complete Web Evidence-to-Claim-to-report citation path.

An opt-in live acceptance test fetches `https://example.com/` twice and verifies stable identity:

```powershell
$env:RUN_WEB_EVIDENCE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest `
  tests/integration/test_web_evidence_infrastructure.py -q
```

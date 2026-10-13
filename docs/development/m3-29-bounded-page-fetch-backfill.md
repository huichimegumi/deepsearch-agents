# M3.29 Bounded page-fetch backfill

## Live boundary after M3.28

The post-M3.28 validation reused `s2sql_041` with the authorized Tavily ceiling of six queries and
six fetched pages. It verified the complete M3.27/M3.28 recovery route:

- ordinary research consumed four queries;
- backend entity recovery consumed the two reserved queries;
- the resolver ran twice instead of stopping at missing context;
- fourteen SQL Evidence records and three Web Evidence records were retained;
- six Claims, cross-source Evidence, and final citations all passed validation.

The run completed in about 95 seconds without an upstream timeout, but the second resolver still
failed closed at `sql_entity_resolution_clues_unsupported`. It made no database value match and no
analytical SQL attempt.

Only three of the six allowed page slots became fetched Web Evidence. The recovery search had two
reserved queries and two reserved page slots, but the search tool clamped `max_results` to the
remaining page count. This supplied only two candidate URLs to the page fetcher. If either candidate
could not be fetched, no later ranked candidate was available to fill the unused successful-page
slot.

## Separate candidate and successful-page limits

M3.29 gives `SearchRequest` a distinct `max_fetched_pages` field. `max_results` remains the bounded
number of deduplicated search candidates, while `max_fetched_pages` limits how many results may
retain successfully fetched full-page content.

The full-page fetcher now works in bounded batches:

1. batch size is at most the number of remaining successful-page slots;
2. successful pages consume slots;
3. failed or empty fetches do not consume slots and allow the next ranked candidate to be tried;
4. fetching stops immediately when the success cap is reached or candidates are exhausted.

Because each batch is no larger than the remaining slot count, concurrent successes cannot exceed
the hard page limit. Ordinary search receives its current non-reserved page allowance from the
shared run budget. Entity recovery asks for at most six candidates—three per reserved page—but may
still retain no more than its two released page slots. Tavily query accounting and the global 6/6
limits are unchanged.

## Verification

Tests cover failed top-ranked page fetches followed by successful lower-ranked backfill, verify that
the fetcher stops at two successes, and assert that the production search tool passes an independent
page cap without shrinking the candidate pool. Existing partial-Web and zero-Web entity recovery
tests continue to pass with the larger bounded candidate pool.

Validation for this stage:

- focused search, runtime, and entity-recovery tests: 54 passed;
- Ruff checks for all changed Python files: passed;
- full repository suite: 186 passed, 6 skipped.

No post-fix Tavily run is performed in M3.29. The next fixed 6/6 validation should confirm that
recovery can fill both reserved Web Evidence page slots when top candidates include an unfetchable
URL, then expose the next content-free entity category or proceed to database value matching.

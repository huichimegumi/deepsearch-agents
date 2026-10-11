# M3.5 Hybrid phase budget alignment

The first one-task validation after M3.4 never reached schema discovery, SQL, or Web search. The
trace showed that the `standard` 180-second profile assigned 18 seconds to clarification and 90
seconds to supervisor research. Both phases timed out before the model produced a research tool
call, while the run still finished with 56 seconds unused.

HybridDeepResearch tasks require both database and Web work and therefore use the existing
`deep_report` time profile from M3.5 onward. This provides a 300-second run envelope and up to 150
seconds for supervisor research. It does not expand external retrieval:

- search queries remain capped at two per task;
- fetched pages remain capped at two per task;
- research rounds remain capped at one;
- the search backend remains hard-locked by the runner;
- paid or mixed backends still require explicit authorization.

The smoke report now records `research_budget_profile` so results cannot silently mix the old
standard profile with the deep-report profile. A unit test fixes the intended relationship: more
model time, unchanged search and page limits.

# Application index — company extraction contract

`applications/index_companies.py` and `applications/skip_resolver.py` share normalization and skip matching for L1 scrape and L2 triage.

## Normalization

`normalize_company_key(s)`:

1. HTML-unescape
2. Lowercase
3. Strip non-alphanumeric characters

## Skip list sources (`SkipResolver.bootstrap`)

| Source | Path (default) |
|--------|----------------|
| File | `applications/skip_companies.txt` (override via `paths.skip_companies` in profile) |
| Applied index | Companies parsed from `applications/application_index.html` |
| Pre-assessment SKIP | `applications/<slug>/pre_assessment.md` with `## Verdict: … SKIP` |

**Missing skip file:** empty file-backed set + warning (no bundled personal fallback list).

## Matching rules

- Keys shorter than 4 characters after normalization are dropped (logged).
- `company_matches_skip_key` uses prefix match with suffix guard (legal suffixes / long keys).
- `hint_matches_skip_company_bidirectional` supports staffing-wrapper hints (≥4 chars).

## §10 — Operational notes

- Call `invalidate_default_cache()` after mutating the in-process skip set in tests.
- Triage calls `reload_runtime_config()` at startup (referral status, ILS matrix/overrides, skip resolver from active profile). Scrape path bootstraps skip resolver at import; use `refresh_skip_resolver()` after profile path changes in long-lived processes.

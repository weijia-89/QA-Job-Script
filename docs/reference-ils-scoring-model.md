# ILS scoring reference (bundle scope)

This repo ships a **conservative point estimate** for triage post-gates, not a full manual ILS research session.

## Pipeline role

| Stage | Module | Output |
|-------|--------|--------|
| L1 scrape | `jobspy/run_search_locally.py` | `priority`, prescreen columns |
| L2 triage | `scripts/triage_jobspy_csv.py` | `triage_verdict`, `ils_estimate` |

When `--ils-floor` is enabled, rows below the effective floor are skipped after arrangement checks.

## Estimate sources (in order)

1. **Company overrides** — `config/company_ils_overrides.json` (optional) merged with `config/company_ils_overrides.example.json`. Override `kind` values:
   - `flat` — `{ "score", "note" }`
   - `nuclear_travel` — base score minus JD travel % penalty (`jobspy/ils_matrix.compute_travel_penalty`)
   - `jd_comp_band` — low vs default score from JD salary patterns
   - `company_or_jd_head` — company substring and/or early-JD keyword
2. **JD-derived fallback** — D1–D5 formula from `config/ils_matrix.yaml` (`jobspy/ils_matrix.jd_derived_ils_fallback`)

See [ils-matrix.md](ils-matrix.md) for dimension tuning.

## Referral-aware floors

`referrals.status_file` entries (`cold` / `warm` / `strong`) adjust the CLI `--ils-floor` via deltas in `profile.yaml` (`ils.referral_warm_delta`, `ils.referral_strong_delta`).

## Out of scope

Full manual ILS research sessions, pre_assessment authoring, and calibrated employer research live outside this bundle.

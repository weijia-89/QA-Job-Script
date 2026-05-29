# ILS scoring reference (for curious readers)

This page supports [ils-matrix.md](ils-matrix.md). Read that guide first if you are new to ILS. This reference describes **where scores come from** in the code — useful after you have run triage once or twice.

## One-line reminder

**ILS** = Interview Likelihood Score — a conservative JD-based estimate used optionally at triage to skip rows below your floor. Not calibrated research, not a hire guarantee.

## Pipeline role

| Stage | What runs | What you get |
|-------|-----------|--------------|
| L1 scrape | `jobspy/run_search_locally.py` | CSV with `priority`, `stack_hits`, comp columns |
| L2 triage | `scripts/triage_jobspy_csv.py` | `triage_verdict` (`apply` / `review` / `skip`), `ils_estimate` |

ILS **floor skips** happen only when you run triage **without** `--no-post-gates` and pass an `--ils-floor` (default **45**, should match `ils.cold_floor` in your profile).

## Where the number comes from (in order)

1. **Company overrides** — optional `config/company_ils_overrides.json` merged with the bundled example. Use these when **you** researched an employer and want that score instead of the formula.
   - `flat` — fixed `{ "score", "note" }`
   - `nuclear_travel` — base score minus JD travel penalty
   - `jd_comp_band` — low vs default score from salary patterns in the JD
   - `company_or_jd_head` — match on company substring and/or early-JD keywords
2. **JD-derived fallback** — D1–D5 plus travel and clamp from `config/ils_matrix.yaml` (`jobspy/ils_matrix.jd_derived_ils_fallback`)

Implementation: `jobspy/ils_matrix.py`.

## Referral-aware floors

`referrals.status_file` maps company substrings to `warm` or `strong`. Unlisted companies are **cold**.

Profile deltas (`ils.referral_warm_delta`, `ils.referral_strong_delta`) adjust the CLI floor:

| Tier | Default effective floor (when `cold_floor: 45`) |
|------|--------------------------------------------------|
| cold | 45 |
| warm | 35 (45 + (−10)) |
| strong | 25 (45 + (−20)) |

## Out of scope for this bundle

Full manual ILS research, pre-assessment authoring, and calibrated employer studies live outside this repo. The matrix and overrides are **triage helpers**, not a replacement for reading the posting and deciding yourself.

## See also

- [ILS matrix guide](ils-matrix.md) — dimensions, travel bands, examples, defaults
- [Your profile](your-profile.md) — `ils` and `referrals` keys

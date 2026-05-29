# ILS matrix (formula layer)

This bundle can estimate an **Interview Likelihood Score (ILS)** from the job description alone. That number helps triage which rows deserve a deeper research session.

## What this is not

- **Not JFS (job-fit score)** — happiness / tailoring depth; manual research.
- **Not a full ILS session** — calibrated 0–100 with structural caps, D9/D10, and employer-specific nuance.
- **Not legal or hiring advice** — a sorting aid for your own pipeline.

## What it is

A **configurable spreadsheet-style formula** (`config/ils_matrix.yaml`) with five additive dimensions (D1–D5), minus travel penalty, clamped to a min/max band. Optional per-company overrides live in `config/company_ils_overrides.json`.

| Dimension | Plain meaning | Default max |
|-----------|---------------|-------------|
| **D1** | Tool/stack words in the JD match your list | 25 |
| **D2** | Years-of-experience language vs your band | 22 |
| **D3** | Domain bridge (staffing agency, gig labeling, nuclear, etc.) | 20 |
| **D4** | Application method (cold apply baseline in formula) | 7 |
| **D5** | Portfolio signal placeholder in formula | 7 |

**Travel penalty** subtracts points when the JD states high travel %.

Triage uses `ils.cold_floor` from your profile (default 45). Warm/strong referral tiers lower the floor using deltas in the profile.

## Tuning

1. Copy `config/ils_matrix.example.yaml` → `config/ils_matrix.yaml`.
2. Edit `dimensions.d1_stack_match.tools` to match **your** stack.
3. Adjust `year_tiers` under D2 if your experience band differs.
4. Add company overrides only after you have a researched score:

```json
{
  "acme-corp": { "score": 58, "note": "Referral path; strong stack match" }
}
```

## Enable ILS post-gates

Pipeline-only (default for sharing):

```bash
python3 scripts/triage_jobspy_csv.py --latest --no-post-gates
```

With arrangement + ILS floor (uses your matrix + profile):

```bash
python3 scripts/triage_jobspy_csv.py --latest --ils-floor 45
```

For estimate vs full-research scope and override kinds, see [reference_ils_scoring_model.md](reference_ils_scoring_model.md).

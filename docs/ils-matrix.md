# ILS matrix (formula layer)

## What is ILS?

**ILS** means **Interview Likelihood Score** — a 0–100-style number that answers: *“How likely am I to get an interview on this posting, given what the JD says and what I know about the employer?”*

In this repo, ILS is implemented as a **conservative, JD-derived heuristic** for triage post-gates. It is **not** calibrated employer research, **not** a hire probability, and **not** happiness or tailoring-depth scoring. Rows still get an `ils_estimate` column when post-gates are off; the score is informational until you enable the floor.

Manual deep research (reading careers pages, referral paths, structural caps, extra dimensions beyond D1–D5) is a **separate layer** you do outside this bundle. Company override JSON is where you park scores from that work.

---

## What this is not

- A full manual ILS research session with structural caps and employer-specific nuance.
- Legal or hiring advice — a sorting aid for your own pipeline.
- Wired into L1 scrape gates — ILS runs only when L2 triage applies post-gates.

---

## What it is

A **configurable spreadsheet-style formula** in `config/ils_matrix.yaml`: five additive dimensions (D1–D5), minus a **travel penalty**, then clamped to min/max. Triage may also use **per-company overrides** from `config/company_ils_overrides.json` (merged with the bundled example).

Implementation: `jobspy/ils_matrix.py` (`jd_derived_ils_fallback`, `compute_travel_penalty`). Estimate vs override precedence: [reference-ils-scoring-model.md](reference-ils-scoring-model.md).

### Conservative estimate disclaimer

Every automated ILS value is a **deliberately conservative point estimate**. The formula cannot see referrals you have not recorded, weak LinkedIn copy, or employers you have already researched. Expect **under-scoring** on strong wheelhouse roles and **over-scoring** on thin JDs. Tune floors and overrides after you have triaged a batch — do not treat `ils_estimate` as ground truth.

---

## Scoring rubric (D1–D5 + travel + clamp)

Points are summed, travel is subtracted, optional contract penalty applied, then the total is clamped.

| Piece | Plain meaning | Increases score | Decreases score | Default cap / notes |
|-------|---------------|-----------------|-----------------|---------------------|
| **D1 — stack match** | Tool/stack phrases from your matrix appear in the JD | Each tool hit adds `points_per_tool_hit` on top of `base_points` | Fewer hits → lower D1 | Max **25** (`max_points`) |
| **D2 — experience** | Years-of-experience language vs your `year_tiers` | Tier patterns map to higher point values (e.g. 5–7 yr band) | Higher year bars in title/JD; PhD/master’s “required” in JD | Default **14** before tier match; `degree_required_penalty` **3** |
| **D3 — domain bridge** | Employer type and JD framing (staffing, nuclear, gig labeling) | Starts at `default_points` | Staffing firm in company name; staffing language in JD head; nuclear keywords cap D3; gig-work phrases in JD head | Max **20**; nuclear capped at **7** |
| **D4 — application method** | Cold-apply baseline in the formula layer | Fixed default | Not varied per row in JD fallback | Default **7** |
| **D5 — portfolio** | Portfolio-signal placeholder in the formula layer | Fixed default | Not varied per row in JD fallback | Default **7** |
| **Travel penalty** | Stated travel % in the JD | No travel language → **0** penalty | Higher stated % → larger subtraction via `travel_penalty.bands` | Up to **28** at ≥50% travel |
| **Contract penalty** | “Contract” in early JD without “w2” nearby | — | `contract_without_w2_penalty` (default **4**) | Applied before clamp |
| **Clamp** | Keeps heuristic in a bounded band | — | Raw sum above `score_max` or below `score_min` | Default **18–72** |

**Override path (before JD formula):** If `config/company_ils_overrides.json` matches the row, that score wins. Kinds: `flat`, `nuclear_travel` (base minus travel penalty), `jd_comp_band`, `company_or_jd_head`. See [reference-ils-scoring-model.md](reference-ils-scoring-model.md).

---

## How `config/profile.yaml` influences ILS

| Profile key | Role in ILS |
|-------------|-------------|
| `ils.matrix_file` | Path to the D1–D5 YAML (default `config/ils_matrix.yaml`). Also overridable via env `QA_JOB_ILS_MATRIX`. |
| `ils.company_overrides_file` | Gitignored JSON merged on top of `config/company_ils_overrides.example.json` for researched per-employer scores. |
| `ils.cold_floor` | **Your documented cold-tier baseline** (default **45**). Triage compares estimates against the CLI `--ils-floor` value (default **45**). Keep `cold_floor` and `--ils-floor` aligned when you change either. |
| `ils.referral_warm_delta` | Added to the cold baseline for **warm** referrals (default **-10** → floor **35** if cold baseline is 45). |
| `ils.referral_strong_delta` | Added for **strong** referrals (default **-20** → floor **25** if cold baseline is 45). |
| `referrals.status_file` | Maps company substrings → `warm` / `strong`; unlisted companies are **cold**. |

### Referral tiers (`referrals.status_file`)

One line per company: `company_substring,warm` or `company_substring,strong`. Comments start with `#`. Matching is **substring** on the JobSpy `company` field (handles “Acme Corp” vs “Acme Corp (via Indeed)”).

**Example** (`applications/referral_status.txt`):

```
# company_substring,status
acme corp,warm
bigco inc,strong
```

| Tier | Meaning | Effective floor (cold baseline 45, default deltas) |
|------|---------|---------------------------------------------------|
| **cold** | No line, or company not listed | `--ils-floor` (e.g. **45**) |
| **warm** | LinkedIn connection or light path | 45 + (-10) = **35** |
| **strong** | Someone who can refer you | 45 + (-20) = **25** |

Deltas are negative so warm/strong postings can pass with a **lower** ILS estimate.

### Profile examples

```yaml
ils:
  cold_floor: 40          # pass --ils-floor 40 when triaging to match
  referral_warm_delta: -10
  referral_strong_delta: -20
  matrix_file: config/ils_matrix.yaml
  company_overrides_file: config/company_ils_overrides.json
```

```json
{
  "acme-corp": { "score": 58, "note": "Researched: referral + stack fit" }
}
```

---

## Triage: heuristic post-gate (optional)

ILS gating runs **after** pipeline hard gates and arrangement checks. It is **optional** — onboarding does not require tuning ILS before your first scrape.

| Mode | Command | ILS behavior |
|------|---------|--------------|
| Pipeline only | `python3 scripts/triage_jobspy_csv.py --latest --no-post-gates` | No ILS or arrangement post-gates; `ils_estimate` still computed for context |
| Post-gates + floor | `python3 scripts/triage_jobspy_csv.py --latest --ils-floor 45` | Skip when `ils_estimate` &lt; effective floor (referral-adjusted) |

`--no-post-gates` disables **both** arrangement post-gates and ILS floor skips. Manual deep research remains outside this script.

---

## Tuning the matrix

1. Copy `config/ils_matrix.example.yaml` → `config/ils_matrix.yaml` (onboarding does this if missing).
2. Edit `dimensions.d1_stack_match.tools` to match **your** stack.
3. Adjust `year_tiers` under D2 if your experience band differs.
4. Add company overrides only after you have a researched score (see example above).

---

## Related docs

- [Your profile](your-profile.md) — `ils` and `referrals` fields
- [ILS scoring reference](reference-ils-scoring-model.md) — estimate sources and override kinds
- [README](../README.md) — quick start and troubleshooting

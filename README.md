# QA-Job-Script

A **local-only** job search pipeline: scrape listings → filter noise → add prescreen columns → triage to apply / review / skip.

No cloud accounts, no telemetry, no hosted services required.

## What this does

1. **Search** job boards (Indeed, LinkedIn, Google Jobs, Remotive, Greenhouse, Lever, Ashby) with queries aimed at QA/SDET/eval and related IC roles.
2. **Filter** obvious mismatches (wrong stack, wrong country, low pay, blocklisted employers, title noise).
3. **Tag** each row with quick signals (`priority`, `stack_hits`, comp extracted from the JD).
4. **Triage** the CSV again with the same rules plus optional ILS scoring.

## What this does not do

- Write cover letters, resumes, or application packets.
- Run a full **JFS** (job-fit / happiness) research session.
- Guarantee interview odds — ILS here is a **formula + optional overrides**, not a calibrated research score.
- Apply to jobs or log into ATS systems for you.

---

## Quick start

**Fastest path:** run the onboarding script (copies config templates, installs deps, prints next steps).

```bash
chmod +x scripts/onboard.sh
./scripts/onboard.sh
```

Windows (PowerShell): `.\scripts\onboard.ps1`

### macOS / Linux (manual)

```bash
cd QA-Job-Script
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/profile.example.yaml config/profile.yaml
cp config/ils_matrix.example.yaml config/ils_matrix.yaml
cp config/skip_companies.txt.example applications/skip_companies.txt
cp config/application_index.html.example applications/application_index.html

python3 jobspy/run_search_locally.py

python3 scripts/triage_jobspy_csv.py --latest --no-post-gates \
  --out jobspy/results/triage_$(date +%Y%m%d).csv
```

### Windows (PowerShell)

```powershell
cd QA-Job-Script
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy config\profile.example.yaml config\profile.yaml
copy config\ils_matrix.example.yaml config\ils_matrix.yaml
copy config\skip_companies.txt.example applications\skip_companies.txt
copy config\application_index.html.example applications\application_index.html

python jobspy\run_search_locally.py

python scripts\triage_jobspy_csv.py --latest --no-post-gates `
  --out jobspy\results\triage.csv
```

### CMD one-liners (no venv)

```cmd
cd QA-Job-Script
python -m pip install -r requirements.txt
copy config\profile.example.yaml config\profile.yaml
python jobspy\run_search_locally.py
```

---

## Shell aliases (optional)

After setup, install shortcuts:

**bash / zsh**

```bash
chmod +x scripts/install_alias.sh
./scripts/install_alias.sh qa-job
source ~/.zshrc   # or ~/.bashrc
qa-job            # run scraper
qa-job-triage     # pipeline-only triage
qa-job-triage-ils # triage with ILS + arrangement post-gates
```

Custom name: `./scripts/install_alias.sh jobspy-qa`

**PowerShell**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\install_alias.ps1 -AliasName qa-job
. $PROFILE
qa-job
```

**Manual alias (bash/zsh)**

```bash
alias qa-job='cd /path/to/QA-Job-Script && python3 jobspy/run_search_locally.py'
```

---

## Your profile (`config/profile.yaml`)

Copy from `config/profile.example.yaml`. This file is **gitignored** — it holds *your* geography, pay floors, and stack keywords.

| Section | What you set |
|---------|----------------|
| `owner` | Label in logs (any string). |
| `remote_preference` | `fully_remote`, `hybrid_home_metro`, or `any_us_remote`. |
| `home_metro` | `name`, `zip_anchor`, `place_names` — cities you would commute to for hybrid days. |
| `silent_office_hubs` | Non-home cities in the location column that imply onsite when the JD is silent. |
| `comp` | `min_ceiling_usd`, `min_floor_usd`, `hourly_annual_floor_usd`, `gate2_floor_usd`. |
| `prescreen.stack_keywords` | Words counted in `stack_hits`. |
| `prescreen.priority` | Year caps for HIGH/MOD/LOW priority flags. |
| `ils` | `cold_floor`, referral deltas, paths to matrix + overrides. |
| `referrals.status_file` | `company_substring,cold\|warm\|strong` per line. |
| `paths` | Skip list, application index HTML, results directory, ops rollup dir. |
| `tracks.enable` | Subset of `A,B,C,G,R,GH,L,AS` scrape tracks (see `profile.example.yaml`). |
| `verified_remote_employers` | Bypass arrangement gate when LinkedIn JD is misleading. |
| `review_companies` | Pass gates but `triage_verdict=review`. |

Validate:

```bash
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

Override path: `export QA_JOB_PROFILE=/path/to/profile.yaml`

---

## ILS matrix (`config/ils_matrix.yaml`)

Copy from `config/ils_matrix.example.yaml`. Controls the **JD-derived** ILS formula (D1–D5, travel bands, score clamp).

See [docs/ILS_MATRIX.md](docs/ILS_MATRIX.md) for dimension meanings and tuning.

Optional per-company scores: copy `config/company_ils_overrides.example.json` → `config/company_ils_overrides.json`.

**Pipeline only (default for sharing):**

```bash
python3 scripts/triage_jobspy_csv.py --latest --no-post-gates
```

**With ILS + arrangement post-gates:**

```bash
python3 scripts/triage_jobspy_csv.py --latest --ils-floor 45
```

---

## First-run checklist

- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] Virtualenv created and `pip install -r requirements.txt` succeeded
- [ ] `config/profile.yaml` exists (copied from example and edited)
- [ ] `applications/skip_companies.txt` exists (even if empty except comments)
- [ ] `applications/application_index.html` exists (minimal empty table is fine)
- [ ] First scrape: `python3 jobspy/run_search_locally.py` writes `jobspy/results/jobspy_results_YYYYMMDD.csv`
- [ ] Triage: `python3 scripts/triage_jobspy_csv.py --latest --no-post-gates`
- [ ] (Optional) Aliases installed via `scripts/install_alias.sh` or `.ps1`

---

## Layout

| Path | Role |
|------|------|
| `jobspy/run_search_locally.py` | Daily scrape + L1 filters + prescreen columns |
| `jobspy/profile_loader.py` | Loads `config/profile.yaml` |
| `jobspy/paths.py` | Canonical repo path constants |
| `jobspy/ils_matrix.py` | Loads `config/ils_matrix.yaml` for ILS formula |
| `applications/prescreen.py` | `stack_hits`, `priority`, `domain`, comp columns |
| `applications/skip_resolver.py` | Skip list + applied-index slugs |
| `scripts/triage_jobspy_csv.py` | Second-pass `triage_verdict` |
| `config/*.example` | Templates only — no personal data shipped |

---

## ATS company lists

Bundled examples: `config/ats_companies_{ashby,gh,lever}.example.txt`.

Override without editing Python:

- `jobspy/results/companies_ashby.txt` (etc.) — replaces bundled list when present
- `jobspy/results/extra_ashby.txt` — append slugs per run

## Security hygiene

Periodically audit dependencies (optional, local-only):

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

Pin versions in `requirements.txt` when you need reproducible installs; a lockfile is optional for this bundle.

## Tests

```bash
QA_JOB_PROFILE=config/profile.test.yaml python3 -m pytest -q
python3 -m py_compile jobspy/run_search_locally.py jobspy/profile_loader.py jobspy/ils_matrix.py
```

Tests use `config/profile.test.yaml` (Atlanta metro fixture) via `QA_JOB_PROFILE`.

---

## Troubleshooting

| Symptom | Likely fix |
|---------|------------|
| `No profile found` | `cp config/profile.example.yaml config/profile.yaml` |
| `PyYAML required` | `pip install pyyaml` |
| `python-jobspy` import error | `pip install python-jobspy` |
| Scrape returns 0 rows | Try `hours_old=336` in code or check network; some boards rate-limit |
| All rows `geo_or_work_mode` fail | Widen `home_metro.place_names` or set `remote_preference: any_us_remote` |
| ILS skips everything | Lower `ils.cold_floor` or use `--no-post-gates` while calibrating |
| Skip list ignored | Ensure `paths.skip_companies` points to your `applications/skip_companies.txt` |

---

## Boundary

Extracted from a personal `toren` workflow (2026-05-29). Canonical development may continue upstream; this bundle is the **shareable**, profile-driven variant.

**Not included:** personal skip lists, `ils_overrides.json` from private repos, JFS/pre_assessment authoring, or agent skills for application packets.

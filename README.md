# QA-Job-Script

A **local-only** job search pipeline: scrape listings → filter noise → add prescreen columns → triage to apply / review / skip.

No cloud accounts, no telemetry, no hosted services required.

## Upstream JobSpy vs this repo

This bundle wraps the open-source [JobSpy library (`python-jobspy`)](https://github.com/cullenwatson/JobSpy) with a **profile-driven** QA/SDET job-search pipeline you run entirely on your machine.

**From JobSpy:** concurrent scraping of Indeed, LinkedIn, Google Jobs, Glassdoor, ZipRecruiter, and other boards; returns raw job rows (title, company, location, description, structured comp when available, job URLs) as a pandas DataFrame you can export to CSV.

**Built on top in this repo:**

- `config/profile.yaml` — your metro, remote/hybrid preference, comp floors, stack keywords, skip paths, scrape tracks
- L1 filters at scrape time and L2 triage — geo/work-mode gates, comp gates, title-noise drops, blocklisted employers
- Prescreen columns — `priority`, `stack_hits`, comp extracted from the JD
- Skip resolver — merges blocklist slugs with companies already in your application index
- Triage CSV — second pass adds `triage_verdict` (`apply` / `review` / `skip`)
- Configurable ILS matrix (`config/ils_matrix.yaml`) plus optional per-company overrides (formula estimate for post-gates, not calibrated research)
- Onboarding scripts (`scripts/onboard.sh` / `.ps1`), shell aliases, pytest fixtures

## What this does

1. **Search** job boards (Indeed, LinkedIn, Google Jobs, Remotive, Greenhouse, Lever, Ashby) with queries aimed at QA/SDET/eval and related IC roles.
2. **Filter** obvious mismatches (wrong stack, wrong country, low pay, blocklisted employers, title noise).
3. **Tag** each row with quick signals (`priority`, `stack_hits`, comp extracted from the JD).
4. **Triage** the CSV again with the same rules plus optional ILS scoring.

## What this does not do

- Write cover letters, resumes, or application packets.
- Run a full manual ILS research session or happiness / tailoring-depth scoring.
- Guarantee interview odds — ILS here is a **formula + optional overrides**, not a calibrated research score.
- Apply to jobs or log into ATS systems for you.

---

## Quick start

**Fastest path:** run the onboarding script (copies config templates, installs deps, prompts you to edit `config/profile.yaml`).

```bash
chmod +x scripts/onboard.sh
./scripts/onboard.sh
```

Windows (PowerShell): `.\scripts\onboard.ps1`

Manual install and platform-specific steps: [docs/installation.md](docs/installation.md)

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

Copy from `config/profile.example.yaml` (onboarding does this automatically). This file is **gitignored** — it holds *your* geography, pay floors, and stack keywords.

**Field-by-field guide:** [docs/your-profile.md](docs/your-profile.md) — what each key means, examples, and what to edit at onboarding vs later.

| Section | What you set |
|---------|----------------|
| `owner` | Label in logs (any string). |
| `remote_preference` | `fully_remote`, `hybrid_home_metro`, or `any_us_remote`. |
| `home_metro` | `name` (display label), `zip_anchor` (home ZIP), `place_names` (substring matching). |
| `silent_office_hubs` | US office cities in the location column when JD is silent on remote — not a travel ban list. |
| `comp` | Scrape pay floors plus `gate2_floor_usd` (threshold for legacy `gate2_at_145k` CSV comp flag). |
| `prescreen.stack_keywords` | Tools/skills counted in `stack_hits`. |
| `prescreen.priority` | Year caps for HIGH/MOD/LOW review flags (not ILS, not a hire score). |
| `ils` | `cold_floor`, referral deltas, paths to matrix + overrides. |
| `referrals.status_file` | `company_substring,warm\|strong` per line (empty file = everyone cold). |
| `paths` | Skip list, optional application index HTML, results directory, ops rollup dir. |
| `tracks.enable` | Subset of `A,B,C,G,R,GH,L,AS` scrape tracks — see [your-profile.md](docs/your-profile.md). |
| `verified_remote_employers` | Bypass arrangement gate when LinkedIn JD is misleading (optional, usually later). |
| `review_companies` | Pass gates but `triage_verdict=review` (optional, usually later). |

Validate:

```bash
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

Override path: `export QA_JOB_PROFILE=/path/to/profile.yaml`

---

## ILS matrix (`config/ils_matrix.yaml`)

Copy from `config/ils_matrix.example.yaml`. Controls the **JD-derived** ILS formula (D1–D5, travel bands, score clamp).

See [docs/ils-matrix.md](docs/ils-matrix.md) for dimension meanings and tuning.

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
- [ ] `config/profile.yaml` exists and is edited for your metro, comp, and stack
- [ ] `applications/skip_companies.txt` exists (even if empty except comments)
- [ ] First scrape: `python3 jobspy/run_search_locally.py` writes `jobspy/results/jobspy_results_YYYYMMDD.csv`
- [ ] Triage: `python3 scripts/triage_jobspy_csv.py --latest --no-post-gates`
- [ ] (Optional) Application index HTML — see [docs/installation.md](docs/installation.md)
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

Tests use `config/profile.test.yaml` (fictional Portland metro fixture) via `QA_JOB_PROFILE`.

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

**Not included:** personal skip lists, `ils_overrides.json` from private repos, pre_assessment authoring, or agent skills for application packets.

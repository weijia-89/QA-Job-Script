# QA-Job-Script

Find QA and SDET job listings on your computer. Drop obvious mismatches. What's left is a short list worth your time, and nothing leaves your machine unless you export it yourself.

No cloud accounts. No telemetry. No hosted dashboards.

---

## About JobSpy

This project builds on the open-source [JobSpy library (`python-jobspy`)](https://github.com/cullenwatson/JobSpy). JobSpy pulls postings from Indeed, LinkedIn, Google Jobs, Glassdoor, ZipRecruiter, and other boards. Each row exports to CSV (title, company, location, description, plus a link column).

QA-Job-Script wires in your profile and filters, then triages the scrape.

---

## What this project does

- **Search** major job boards with queries aimed at QA, SDET, and test automation roles (via JobSpy)
- **Filter** listings that do not match you: wrong geography, remote rules, pay floors, blocklisted employers
- **Tag** each row with quick signals (stack keyword hits, rough priority, pay parsed from the description)
- **Triage** your spreadsheet into apply / review / skip buckets. Optional interview-likelihood scoring can wait until you want it ([docs/ils-matrix.md](docs/ils-matrix.md))
- **Profile-driven setup:** `config/profile.yaml` holds your metro, remote preference, pay floors, stack keywords, and which boards to search. Onboarding scripts (`scripts/onboard.sh`, `scripts/onboard.ps1`) copy templates and walk you through editing it ([docs/your-profile.md](docs/your-profile.md))

---

## What this project does not do

- Write cover letters, resumes, or application packets
- Run manual employer research sessions or produce application strategy documents
- Ship pre-built employer research files or personal skip lists from a private workflow
- Guarantee interviews. Optional ILS is a formula plus your overrides; treat it as a rubric, not a prediction engine
- Apply to jobs or sign into ATS systems for you

---

## Start here (recommended path)

### 1. Get the project on your computer

If you use Git, clone the repo. If not, download the ZIP from GitHub and unzip it.

```bash
git clone https://github.com/weijia-89/QA-Job-Script.git
cd QA-Job-Script
```

### 2. Run onboarding (easier default)

Open **Terminal** (Mac: Applications → Utilities → Terminal) or **PowerShell** (Windows: Start menu → search “PowerShell”). Then run the onboarding script. It checks Python, installs dependencies, and copies starter settings. Then it walks you through editing **your** profile.

**Mac / Linux:**

```bash
chmod +x scripts/onboard.sh
./scripts/onboard.sh
```

**Windows (PowerShell):**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once, if Windows blocks scripts
.\scripts\onboard.ps1
```

When onboarding asks you to edit `config/profile.yaml`, that file is where you set your metro area, pay floors, and skills list. Full walkthrough: **[docs/your-profile.md](docs/your-profile.md)**

### Manual install (step by step)

Use this path if you want to set everything up by hand, or if the onboarding script fails. Full commands for Python, virtual environments, and config templates: **[docs/installation.md](docs/installation.md)**. Or run the onboarding script above instead.

### 3. Run your first search and triage

After onboarding, use the shortcuts it mentions, or run the scraper once (this hits the network and can take several minutes):

```bash
python3 jobspy/run_search_locally.py
python3 scripts/triage_jobspy_csv.py --latest --no-post-gates
```

Results land in `jobspy/results/` as CSV files you can open in Excel, Google Sheets, or Numbers.

**Optional scoring (ILS):** You can ignore this for your first few runs. When you want to understand how “interview likelihood” points work, read **[docs/ils-matrix.md](docs/ils-matrix.md)**. Plain-language guide.

---

## Key settings files (after onboarding)

| File | What it is for |
|------|----------------|
| `config/profile.yaml` | **Start here.** Your geography, pay, skills, referral map. [Guide →](docs/your-profile.md) |
| `config/ils_matrix.yaml` | Optional rubric for interview-likelihood points. [Guide →](docs/ils-matrix.md) |
| `applications/skip_companies.txt` | Companies to always ignore (one per line) |

Both YAML files come from `.example` templates. Git does not commit them; they stay on your machine only.

---

## Shell shortcuts (optional)

After setup, you can install friendly command names so you do not re-type long paths:

**Mac / Linux:** `./scripts/install_alias.sh qa-job` then restart Terminal or run `source ~/.zshrc`

**Windows:** `.\scripts\install_alias.ps1 -AliasName qa-job` then restart PowerShell

Then `qa-job` runs the scraper and `qa-job-triage` runs triage. Details in [docs/installation.md](docs/installation.md).

---

## First-run checklist

- [ ] Python 3.10+ installed
- [ ] Onboarding script finished (`./scripts/onboard.sh` or `.\scripts/onboard.ps1`)
- [ ] `config/profile.yaml` edited for your metro, pay, and stack ([your-profile.md](docs/your-profile.md))
- [ ] First scrape produced a file under `jobspy/results/`
- [ ] Triage run with `--no-post-gates` while you are learning
- [ ] (Later) Read [ils-matrix.md](docs/ils-matrix.md) if you want scoring gates

---

## Troubleshooting (plain language)

| What you see | What to try |
|--------------|-------------|
| **`command not found`** (Mac/Linux) | You may be in the wrong folder. `cd` into the QA-Job-Script folder. If that fails, Python may not be installed; see [installation.md](docs/installation.md). |
| **`python` is not recognized** (Windows) | Install Python from [python.org](https://www.python.org/downloads/) and check “Add Python to PATH” during setup. |
| **`No profile found`** | Run onboarding again, or copy `config/profile.example.yaml` to `config/profile.yaml`. |
| **Script blocked on Windows** | In PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then re-run `.\scripts\onboard.ps1`. |
| **Scrape returns zero rows** | Board responses vary by day. Network or rate limits are common; try again later. Some boards throttle automated access. |
| **Everything says geo or work mode fail** | Widen cities in `home_metro.place_names` or set `remote_preference: any_us_remote` in your profile. |
| **ILS skips almost everything** | Normal while calibrating. Use `--no-post-gates` first, then read [ils-matrix.md](docs/ils-matrix.md) and lower `ils.cold_floor` if needed. |
| **pip shows a corporate Artifactory host or another employer index** | Your machine has a corporate pip index in `pip.conf` or env vars. Re-run onboarding (it forces **pypi.org**), or install manually with the flags in [installation.md](docs/installation.md#public-pypi-only-corporate-pipconf). |
| **`PyYAML required` or import errors** | Re-run onboarding, or install with public PyPI flags from [installation.md](docs/installation.md#public-pypi-only-corporate-pipconf). |

---

<details>
<summary><strong>Advanced: power-user commands and layout</strong></summary>

### Validate profile path

```bash
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

Override: `export QA_JOB_PROFILE=/path/to/profile.yaml`

### Triage with ILS post-gates

```bash
python3 scripts/triage_jobspy_csv.py --latest --ils-floor 45
```

Pipeline-only (no ILS skip): `--no-post-gates`

### Per-company score overrides

Copy `config/company_ils_overrides.example.json` → `config/company_ils_overrides.json`

### Repo layout

| Path | Role |
|------|------|
| `jobspy/run_search_locally.py` | Daily scrape + filters + prescreen columns |
| `jobspy/profile_loader.py` | Loads `config/profile.yaml` |
| `jobspy/ils_matrix.py` | Loads ILS matrix for formula scoring |
| `applications/prescreen.py` | `stack_hits`, `priority`, comp columns |
| `applications/skip_resolver.py` | Skip list + applied-index merge |
| `scripts/triage_jobspy_csv.py` | Second-pass `triage_verdict` |

### ATS company lists

Examples: `config/ats_companies_{ashby,gh,lever}.example.txt`. Override with files under `jobspy/results/`.

### Tests

```bash
QA_JOB_PROFILE=config/profile.test.yaml python3 -m pytest -q
```

### Dependency audit (optional)

```bash
pip install pip-audit && pip-audit -r requirements.txt
```

</details>

---

## Boundary

Extracted from a personal workflow (2026-05-29). This is the **shareable**, profile-driven variant for local use.

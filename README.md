# QA-Job-Script

Find QA and SDET job listings on your computer, filter out obvious mismatches, and get a short list worth your time — **without** signing up for cloud services or sending your data anywhere.

This tool runs entirely on your machine. No accounts, no telemetry, no hosted dashboards.

---

## What problem this solves

Job boards are noisy. You might see hundreds of postings that are wrong city, wrong pay, wrong stack, or employers you already applied to. QA-Job-Script:

1. **Searches** major boards (Indeed, LinkedIn, Google Jobs, and others) with queries aimed at QA / SDET / test automation roles.
2. **Filters** listings that clearly do not match your profile (location, remote rules, pay floors, blocklisted companies).
3. **Tags** each row with quick signals (stack keywords hit, rough priority, pay extracted from the description).
4. **Triages** the spreadsheet into apply / review / skip — with an optional scoring step you can turn on later.

It does **not** write cover letters, submit applications, or log into company career sites for you.

---

## Start here (recommended path)

### 1. Get the project on your computer

If you use Git, clone the repo. If not, download the ZIP from GitHub and unzip it.

```bash
git clone https://github.com/weijia-89/QA-Job-Script.git
cd QA-Job-Script
```

### 2. Open Terminal (Mac) or PowerShell (Windows)

- **Mac:** Terminal is in Applications → Utilities → Terminal. It is a text window where you type commands and press Enter.
- **Windows:** Open **PowerShell** from the Start menu (search “PowerShell”). Same idea — a window for typed commands.

Step-by-step install details (Python, virtual environment, paths): **[docs/installation.md](docs/installation.md)**

### 3. Run the onboarding script

The onboarding script checks Python, installs what the tool needs, copies starter settings files, and walks you through editing **your** profile.

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

### 4. Run your first search and triage

After onboarding, use the shortcuts it mentions, or run the scraper once (this hits the network and can take several minutes):

```bash
python3 jobspy/run_search_locally.py
python3 scripts/triage_jobspy_csv.py --latest --no-post-gates
```

Results land in `jobspy/results/` as CSV files you can open in Excel, Google Sheets, or Numbers.

**Optional scoring (ILS):** You can ignore this for your first few runs. When you want to understand how “interview likelihood” points work, read **[docs/ils-matrix.md](docs/ils-matrix.md)** — plain-language guide, not a developer spec.

---

## Upstream JobSpy vs this repo

This bundle wraps the open-source [JobSpy library (`python-jobspy`)](https://github.com/cullenwatson/JobSpy).

**JobSpy provides:** scraping from Indeed, LinkedIn, Google Jobs, Glassdoor, ZipRecruiter, and other boards — raw rows (title, company, location, description, links) as data you can save to CSV.

**This repo adds on top:**

- **`config/profile.yaml`** — your metro, remote preference, pay floors, stack keywords, which boards to search
- **Filters** — drop wrong geography, low pay, title noise, blocklisted employers
- **Prescreen columns** — `priority`, `stack_hits`, pay parsed from the description
- **Triage** — second pass labels each row `apply`, `review`, or `skip`
- **Optional ILS scoring** — configurable “how promising is this posting?” formula ([docs/ils-matrix.md](docs/ils-matrix.md))
- **Onboarding scripts** — `scripts/onboard.sh` and `scripts/onboard.ps1`

---

## Key settings files (after onboarding)

| File | What it is for |
|------|----------------|
| `config/profile.yaml` | **Start here.** Your geography, pay, skills, referral map. [Guide →](docs/your-profile.md) |
| `config/ils_matrix.yaml` | Optional rubric for interview-likelihood points. [Guide →](docs/ils-matrix.md) |
| `applications/skip_companies.txt` | Companies to always ignore (one per line) |

Both YAML files are copied from `.example` templates and are **not** committed to git — they stay on your machine only.

---

## Shell shortcuts (optional)

After setup, you can install friendly command names so you do not re-type long paths:

**Mac / Linux:** `./scripts/install_alias.sh qa-job` then restart Terminal or run `source ~/.zshrc`

**Windows:** `.\scripts\install_alias.ps1 -AliasName qa-job` then restart PowerShell

Then `qa-job` runs the scraper and `qa-job-triage` runs triage. Details in [docs/installation.md](docs/installation.md).

---

## First-run checklist

- [ ] Python 3.10+ installed
- [ ] Onboarding script finished (`./scripts/onboard.sh` or `.\scripts\onboard.ps1`)
- [ ] `config/profile.yaml` edited for your metro, pay, and stack — [your-profile.md](docs/your-profile.md)
- [ ] First scrape produced a file under `jobspy/results/`
- [ ] Triage run with `--no-post-gates` while you are learning
- [ ] (Later) Read [ils-matrix.md](docs/ils-matrix.md) if you want scoring gates

---

## Troubleshooting (plain language)

| What you see | What to try |
|--------------|-------------|
| **`command not found`** (Mac/Linux) | You may be in the wrong folder — `cd` into the QA-Job-Script folder. Or Python is not installed — see [installation.md](docs/installation.md). |
| **`python` is not recognized** (Windows) | Install Python from [python.org](https://www.python.org/downloads/) and check “Add Python to PATH” during setup. |
| **`No profile found`** | Run onboarding again, or copy `config/profile.example.yaml` to `config/profile.yaml`. |
| **Script blocked on Windows** | In PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then re-run `.\scripts\onboard.ps1`. |
| **Scrape returns zero rows** | Network or rate limits on job boards — try again later; some boards throttle automated access. |
| **Everything says geo or work mode fail** | Widen cities in `home_metro.place_names` or set `remote_preference: any_us_remote` in your profile. |
| **ILS skips almost everything** | Normal while calibrating — use `--no-post-gates` first, then read [ils-matrix.md](docs/ils-matrix.md) and lower `ils.cold_floor` if needed. |
| **`PyYAML required` or import errors** | Re-run onboarding step 3, or: `pip install -r requirements.txt` inside your project folder. |

---

## What this does not do

- Write cover letters, resumes, or application packets.
- Run a full manual employer research session.
- Guarantee interviews — optional ILS is a formula plus your overrides, not a calibrated prediction.
- Apply to jobs or sign into ATS systems for you.

---

<details>
<summary><strong>Advanced — power-user commands and layout</strong></summary>

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

Extracted from a personal workflow (2026-05-29). This is the **shareable**, profile-driven variant — not a hosted product.

**Not included:** personal skip lists from private repos, pre-built employer research files, or tools that submit applications for you.

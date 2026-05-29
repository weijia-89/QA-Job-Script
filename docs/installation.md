# Installation

Manual setup for macOS, Linux, and Windows. For the fastest path, use the onboarding scripts instead:

- macOS / Linux: `./scripts/onboard.sh`
- Windows: `.\scripts\onboard.ps1`

Onboarding copies config templates, installs dependencies, and prompts you to edit `config/profile.yaml` immediately.

This repo layers profile-driven filters, prescreen columns, and triage on top of the upstream [JobSpy library (`python-jobspy`)](https://github.com/cullenwatson/JobSpy); see the [README introduction](../README.md#upstream-jobspy-vs-this-repo) for what the library provides vs what this bundle adds.

---

## macOS / Linux

```bash
cd QA-Job-Script
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/profile.example.yaml config/profile.yaml
cp config/ils_matrix.example.yaml config/ils_matrix.yaml
cp config/skip_companies.txt.example applications/skip_companies.txt

# Edit profile before your first scrape (metro, comp floors, stack keywords).
${EDITOR:-nano} config/profile.yaml

python3 jobspy/run_search_locally.py

python3 scripts/triage_jobspy_csv.py --latest --no-post-gates \
  --out jobspy/results/triage_$(date +%Y%m%d).csv
```

## Windows (PowerShell)

```powershell
cd QA-Job-Script
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy config\profile.example.yaml config\profile.yaml
copy config\ils_matrix.example.yaml config\ils_matrix.yaml
copy config\skip_companies.txt.example applications\skip_companies.txt

notepad config\profile.yaml   # or your editor

python jobspy\run_search_locally.py

python scripts\triage_jobspy_csv.py --latest --no-post-gates `
  --out jobspy\results\triage.csv
```

## Windows (CMD, no venv)

```cmd
cd QA-Job-Script
python -m pip install -r requirements.txt
copy config\profile.example.yaml config\profile.yaml
python jobspy\run_search_locally.py
```

---

## Application index (optional / advanced)

Some users maintain an HTML table of roles they have already applied to. The scraper can merge company names from that file into the auto-skip set.

- Default path (if you use it): `applications/application_index.html`
- Set `paths.application_index` in `config/profile.yaml` to your file, or omit the key to use the default under `applications/`.
- Format contract: [application-index-company-extraction-contract.md](application-index-company-extraction-contract.md)

You do **not** need an application index for a minimal fork. An empty skip list (`applications/skip_companies.txt` with only comments) is enough to start.

---

## Verify install

```bash
QA_JOB_PROFILE=config/profile.test.yaml python3 -m pytest -q
python3 scripts/triage_jobspy_csv.py --help
python3 -c "from jobspy.profile_loader import get_profile; print(get_profile()['_meta']['path'])"
```

---

## Optional: shell aliases

See [README.md](../README.md#shell-aliases-optional) for `install_alias.sh` / `install_alias.ps1`.

## Optional: dependency audit

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

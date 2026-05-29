# Installation

Manual setup for macOS, Linux, and Windows. For the fastest path, use the onboarding scripts instead:

- macOS / Linux: `./scripts/onboard.sh`
- Windows: `.\scripts\onboard.ps1`

Onboarding copies config templates, installs dependencies, and prompts you to edit `config/profile.yaml` immediately. See [your-profile.md](your-profile.md) for a field-by-field guide.

For how this bundle relates to JobSpy and what it adds on top, see [About JobSpy](../README.md#about-jobspy) and [What this project does](../README.md#what-this-project-does) in the README.

### Public PyPI only (corporate `pip.conf`)

This bundle installs from **https://pypi.org** only. If your employer sets a global pip index (`pip.conf`, `PIP_INDEX_URL`, or an Artifactory mirror such as `artifact.intuit.com`), onboarding and the commands below clear those overrides and pass `--index-url https://pypi.org/simple` so installs do not use a private index.

---

## macOS / Linux

```bash
cd QA-Job-Script
python3 -m venv .venv
source .venv/bin/activate
env -u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL pip install -r requirements.txt \
  --index-url https://pypi.org/simple \
  --trusted-host pypi.org

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
$env:PIP_INDEX_URL = $null
$env:PIP_EXTRA_INDEX_URL = $null
pip install -r requirements.txt `
  --index-url https://pypi.org/simple `
  --trusted-host pypi.org

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
$env:PIP_INDEX_URL = $null; $env:PIP_EXTRA_INDEX_URL = $null
python -m pip install -r requirements.txt --index-url https://pypi.org/simple --trusted-host pypi.org
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

# Security Policy

## Supported versions

| Version / branch | Supported |
|------------------|-----------|
| `main` (latest commit) | Yes |
| Latest tagged release on GitHub (if any) | Yes |
| Older forks or snapshots | No — use `main` or open an issue |

This project does not publish a separate long-term support branch. Security fixes land on `main`.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately using one of:

1. **[GitHub private security advisory](https://github.com/weijia-89/QA-Job-Script/security/advisories/new)** (preferred for this repository)
2. Or contact the repository owner through GitHub with details you do not want public

Include: affected component (script, dependency, docs), steps to reproduce, impact, and any suggested fix if you have one.

We aim to acknowledge reports within a reasonable timeframe and will coordinate disclosure after a fix or documented mitigation.

## Security posture (summary)

This bundle is designed for **local-only** use:

- **No telemetry** — the tooling does not phone home, embed analytics SDKs, or require cloud accounts.
- **Network use** — Job board scraping (`python-jobspy`) and `pip install` hit the network; everything else runs on your machine.
- **Secrets stay local** — personal paths such as `config/profile.yaml`, `config/ils_matrix.yaml`, `applications/skip_companies.txt`, and `jobspy/results/*.csv` are listed in `.gitignore` and must not be committed.
- **Install hardening** — onboarding clears corporate pip index overrides and installs from [public PyPI](docs/installation.md#public-pypi-only-corporate-pipconf); shell alias installers validate alias names before writing to your shell config.
- **Dependency audit** — run periodically in your virtual environment:

  ```bash
  pip install pip-audit
  pip-audit -r requirements.txt
  ```

  See also the optional audit note in [README.md](README.md#dependency-audit-optional) (Advanced section).

### Transitive dependency note (`markdownify`)

`python-jobspy` pulls in **`markdownify`** transitively (not pinned directly in this repo). Older `markdownify` versions may be flagged by `pip-audit` (for example **CVE-2025-46656**, fixed in `markdownify` **0.14.1**). Mitigation options:

- Re-run `pip-audit` after upgrading `python-jobspy` or refreshing your venv.
- Track upstream [JobSpy](https://github.com/cullenwatson/JobSpy) releases for dependency bumps.
- If audit output blocks you, document the finding and upgrade paths in your local environment; do not commit job data or profile files while testing.

This project does not vendor JobSpy; dependency CVEs are ultimately resolved upstream or by your local pin/upgrade choices within `requirements.txt` bounds.

## What not to commit

Never commit personal or sensitive material to the shared repository:

| Path / pattern | Why |
|----------------|-----|
| `config/profile.yaml` | Pay floors, metro, skills, referral maps |
| `config/ils_matrix.yaml` | Personal scoring rubric |
| `config/company_ils_overrides.json` | Per-company overrides |
| `applications/skip_companies.txt` | Blocklist |
| `applications/application_index.html` | Applied roles index |
| `jobspy/results/*.csv` (and related logs/JSON) | Scraped job listings |

Use `.example` templates only in Git. If something was committed by mistake, rotate any exposed secrets, remove the file from history if needed, and open a private advisory if the leak is security-sensitive.

## Installation and corporate environments

For manual install, public-PyPI-only flags, and corporate `pip.conf` behavior, see **[docs/installation.md](docs/installation.md)** (especially [Public PyPI only](docs/installation.md#public-pypi-only-corporate-pipconf)).

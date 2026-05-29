# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where applicable.

## [Unreleased]

_Nothing yet._

## [1.0.0] - 2026-05-29

First public release of the shareable, profile-driven JobSpy pipeline for local QA/SDET job search and triage.

### Added

- Profile-driven scrape and triage: `jobspy/run_search_locally.py`, `scripts/triage_jobspy_csv.py`, prescreen and skip resolution
- Onboarding scripts (`scripts/onboard.sh`, `scripts/onboard.ps1`) with template copies for profile, ILS matrix, and skip lists
- Interactive profile setup (`scripts/configure_profile.py`) with sensible defaults during onboarding
- Documentation set: [your-profile](docs/your-profile.md), [ILS matrix](docs/ils-matrix.md), [installation](docs/installation.md), JobSpy upstream scope, application-index contract, ops rollup
- Optional shell shortcuts via `scripts/install_alias.sh` and `scripts/install_alias.ps1`
- Example configs and test profile for `pytest` without personal data

### Changed

- Onboarding-first README install path; beginner-friendly troubleshooting and first-run checklist
- README deAI pass: clearer local-only privacy wording and deduplicated scope sections
- Force **public PyPI** (`pypi.org`) during onboarding and manual install when corporate `pip.conf` or `PIP_INDEX_URL` is set — see [installation.md](docs/installation.md#public-pypi-only-corporate-pipconf)
- Expanded ILS definition, rubric, and profile mapping in docs
- Removed author-specific employer slugs from test fixtures and documentation examples

### Security

- Hardened onboarding: array-based `pip` invocation in `onboard.sh`, upper bounds on dependency pins in `requirements.txt`, `.gitignore` for virtualenv directories
- Shell alias installers validate alias names before appending to `~/.zshrc` / PowerShell profile
- Personal config paths remain gitignored (`profile.yaml`, ILS matrix, skip lists, scrape results) — see [SECURITY.md](SECURITY.md)

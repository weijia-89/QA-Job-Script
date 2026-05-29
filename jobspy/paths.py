"""Canonical filesystem paths for the QA-Job-Script bundle."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JOBSPY_DIR = REPO_ROOT / "jobspy"
RESULTS_DIR = JOBSPY_DIR / "results"
APPLICATIONS_DIR = REPO_ROOT / "applications"
CONFIG_DIR = REPO_ROOT / "config"

PROFILE_YAML = CONFIG_DIR / "profile.yaml"
PROFILE_EXAMPLE = CONFIG_DIR / "profile.example.yaml"
ILS_MATRIX_YAML = CONFIG_DIR / "ils_matrix.yaml"
ILS_MATRIX_EXAMPLE = CONFIG_DIR / "ils_matrix.example.yaml"
COMPANY_ILS_OVERRIDES = CONFIG_DIR / "company_ils_overrides.json"

SKIP_COMPANIES_TXT = APPLICATIONS_DIR / "skip_companies.txt"
APPLICATION_INDEX_HTML = APPLICATIONS_DIR / "application_index.html"
REFERRAL_STATUS_TXT = APPLICATIONS_DIR / "referral_status.txt"

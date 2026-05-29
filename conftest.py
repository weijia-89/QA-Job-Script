"""Shared pytest fixtures for QA-Job-Script."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session", autouse=True)
def _default_test_profile() -> None:
    os.environ.setdefault(
        "QA_JOB_PROFILE",
        str(REPO_ROOT / "config" / "profile.test.yaml"),
    )


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def applications_dir(repo_root: Path) -> Path:
    path = repo_root / "applications"
    sys.path.insert(0, str(path))
    return path

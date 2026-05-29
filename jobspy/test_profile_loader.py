"""Tests for profile_loader path expansion and track gating."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "jobspy"))

import profile_loader as pl  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_profile_cache() -> None:
    pl.get_profile.cache_clear()
    yield
    pl.get_profile.cache_clear()


def test_enabled_tracks_reads_profile_fixture() -> None:
    os.environ["QA_JOB_PROFILE"] = str(_REPO / "config" / "profile.test.yaml")
    pl.reload_profile()

    assert pl.enabled_tracks() == frozenset({"A"})


def test_enabled_tracks_defaults_all_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_JOB_PROFILE", str(_REPO / "config" / "profile.test.yaml"))
    pl.reload_profile()
    profile = pl.get_profile()
    profile.pop("tracks", None)
    monkeypatch.setattr(pl, "get_profile", lambda: profile)

    assert pl.enabled_tracks() == frozenset({"A", "B", "C", "G", "R", "GH", "L", "AS"})


def test_enabled_tracks_empty_list_falls_back_to_track_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QA_JOB_PROFILE", str(_REPO / "config" / "profile.test.yaml"))
    pl.reload_profile()
    profile = pl.get_profile()
    profile["tracks"] = {"enable": []}
    monkeypatch.setattr(pl, "get_profile", lambda: profile)

    assert pl.enabled_tracks() == frozenset({"A"})


def test_profile_expands_repo_relative_paths() -> None:
    os.environ["QA_JOB_PROFILE"] = str(_REPO / "config" / "profile.test.yaml")
    profile = pl.reload_profile()
    paths = profile["paths"]

    skip_path = Path(paths["skip_companies"])
    assert skip_path.is_absolute()
    assert skip_path.name == "skip_companies.test.txt"
    assert (_REPO / "config" / "skip_companies.test.txt") == skip_path


def test_ops_rollup_dir_default_under_jobspy_results() -> None:
    os.environ["QA_JOB_PROFILE"] = str(_REPO / "config" / "profile.test.yaml")
    pl.reload_profile()

    assert pl.ops_rollup_dir() == _REPO / "jobspy" / "results" / "ops_rollups"

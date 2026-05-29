"""Tests for skip_resolver bootstrap and matching."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "applications"))

from skip_resolver import (  # noqa: E402
    SkipResolver,
    build_normalized_skip_keys,
    company_matches_skip_key,
    get_resolver,
    install_resolver,
    normalize_company_key,
    rebootstrap_from_profile,
)


@pytest.fixture
def empty_bootstrap_dirs(tmp_path: Path) -> tuple[str, str, str]:
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    skip_path = tmp_path / "missing_skip_companies.txt"
    index_path = tmp_path / "application_index.html"
    index_path.write_text(
        "<html><body><table></table></body></html>",
        encoding="utf-8",
    )
    return str(apps_dir), str(skip_path), str(index_path)


def test_bootstrap_missing_skip_file_uses_empty_file_backed_set(
    empty_bootstrap_dirs: tuple[str, str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    apps_dir, skip_path, index_path = empty_bootstrap_dirs
    with caplog.at_level(logging.WARNING):
        resolver = SkipResolver.bootstrap(apps_dir, skip_path, index_path)

    assert resolver.raw_skip_companies == set()
    assert any(
        "skip_companies file unavailable" in record.message
        for record in caplog.records
    )


def test_bootstrap_missing_skip_file_does_not_inject_bundled_slugs(
    empty_bootstrap_dirs: tuple[str, str, str],
) -> None:
    apps_dir, skip_path, index_path = empty_bootstrap_dirs
    resolver = SkipResolver.bootstrap(apps_dir, skip_path, index_path)

    for slug in ("intuit", "scale ai", "anduril", "peek"):
        assert slug not in resolver.raw_skip_companies
        assert resolver.is_skip_company(slug) is False


def test_bootstrap_loads_skip_file_entries(tmp_path: Path) -> None:
    apps_dir = tmp_path / "applications"
    apps_dir.mkdir()
    skip_path = tmp_path / "skip_companies.txt"
    skip_path.write_text("acme corp\n# comment\n", encoding="utf-8")
    index_path = tmp_path / "application_index.html"
    index_path.write_text("<html></html>", encoding="utf-8")

    resolver = SkipResolver.bootstrap(str(apps_dir), str(skip_path), str(index_path))

    assert "acme corp" in resolver.raw_skip_companies
    assert resolver.is_skip_company("Acme Corp LLC") is True


@pytest.mark.parametrize(
    "company_norm,skip_key,expected",
    [
        ("acmecorp", "acme", True),
        ("checkpointsystems", "peek", False),
        ("intuit", "intuit", True),
        ("intuitivesurgical", "intuit", False),
    ],
)
def test_company_matches_skip_key_prefix_guard(
    company_norm: str,
    skip_key: str,
    expected: bool,
) -> None:
    assert company_matches_skip_key(company_norm, skip_key) is expected


def test_build_normalized_skip_keys_drops_short_entries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        keys = build_normalized_skip_keys(["ab", "validcorp"])

    assert "validcorp" in keys
    assert "ab" not in keys
    assert any("dropping" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acme Corp", "acmecorp"),
        ("Super.com", "supercom"),
        ("", ""),
    ],
)
def test_normalize_company_key(raw: str, expected: str) -> None:
    assert normalize_company_key(raw) == expected


def test_hint_matches_skip_company_bidirectional_prefix() -> None:
    resolver = SkipResolver({"intuit", "scale ai"})
    assert resolver.hint_matches_skip_company_bidirectional("Intuit Inc") is True
    assert resolver.hint_matches_skip_company_bidirectional("Scale") is True
    assert resolver.hint_matches_skip_company_bidirectional("ab") is False
    assert resolver.hint_matches_skip_company_bidirectional("Anthropic") is False


def test_rebootstrap_from_profile_uses_active_profile_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.path.insert(0, str(_REPO / "jobspy"))
    import profile_loader as pl  # noqa: E402

    test_profile = str(_REPO / "config" / "profile.test.yaml")
    empty_skip = tmp_path / "empty_skip.txt"
    empty_skip.write_text("# empty\n", encoding="utf-8")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        f"paths:\n"
        f"  skip_companies: {empty_skip}\n"
        f"  application_index: {_REPO / 'config/application_index.test.html'}\n",
        encoding="utf-8",
    )

    seeded = SkipResolver({"intuit"})
    install_resolver(seeded)
    assert get_resolver().is_skip_company("Intuit") is True

    try:
        monkeypatch.setenv("QA_JOB_PROFILE", str(profile_path))
        pl.reload_profile()
        rebootstrap_from_profile(str(_REPO / "applications"))
        assert get_resolver().is_skip_company("Intuit") is False
    finally:
        monkeypatch.setenv("QA_JOB_PROFILE", test_profile)
        pl.reload_profile()
        rebootstrap_from_profile(str(_REPO / "applications"))
        import run_search_locally as rsl  # noqa: E402

        rsl.refresh_skip_resolver()

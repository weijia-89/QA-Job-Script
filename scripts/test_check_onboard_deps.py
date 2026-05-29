"""Tests for check_onboard_deps.py requirement parsing and assessment."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import check_onboard_deps as cod  # noqa: E402


def test_parse_requirement_line() -> None:
    req = cod.Requirement.parse_line("pandas>=2.0,<3")
    assert req is not None
    assert req.name == "pandas"
    assert req.lower == "2.0"
    assert req.upper == "3"


def test_version_satisfies_bounds() -> None:
    assert cod._version_satisfies("2.2.0", "2.0", "3")
    assert not cod._version_satisfies("1.9.0", "2.0", "3")
    assert not cod._version_satisfies("3.0.0", "2.0", "3")


def test_assess_requirements_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cod, "_installed_version", lambda _name: None)
    monkeypatch.setattr(cod, "_importable", lambda _mod: False)
    reqs = [
        cod.Requirement("pandas", "2.0", "3"),
        cod.Requirement("pyyaml", "6.0", "7"),
    ]
    ok, statuses = cod.assess_requirements(reqs)
    assert not ok
    assert all(not s.ok for s in statuses)


def test_assess_requirements_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    versions = {
        "pandas": "2.2.0",
        "requests": "2.31.0",
        "python-jobspy": "1.1.80",
        "pytest": "8.0.0",
        "pyyaml": "6.0.1",
    }
    monkeypatch.setattr(
        cod, "_installed_version", lambda name: versions.get(name)
    )
    monkeypatch.setattr(cod, "_importable", lambda _mod: True)
    ok, statuses = cod.assess_requirements(cod.load_requirements())
    assert ok
    assert all(s.ok for s in statuses)


def test_main_check_only_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cod, "assess_requirements", lambda _reqs=None: (True, []))
    assert cod.main(["--check-only"]) == 0
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(cod, "assess_requirements", lambda _reqs=None: (False, []))
    assert cod.main(["--check-only"]) == 1

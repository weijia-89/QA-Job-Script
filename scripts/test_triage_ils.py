"""Table-driven tests for triage ILS estimate and referral floors."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("QA_JOB_PROFILE", str(_REPO / "config" / "profile.test.yaml"))
sys.path.insert(0, str(_REPO / "jobspy"))
sys.path.insert(0, str(_REPO / "scripts"))

from ils_matrix import jd_derived_ils_fallback, load_company_overrides, score_company_override  # noqa: E402
import triage_jobspy_csv as triage  # noqa: E402


@pytest.mark.parametrize(
    "company,desc,expect_min,expect_max,note_sub",
    [
        ("Anthropic", "playwright python pytest senior QA automation", 18, 72, "jd_derived"),
        ("Westinghouse Electric", "travel 30-40% nuclear QA", 10, 45, "travel_penalty"),
        ("Conduent", "salary range $85,000 - $95,000 automation", 40, 42, "85"),
        ("Conduent", "senior QA engineer remote US", 43, 45, "BPO"),
        ("Doma Health", "FHIR QA lead remote", 48, 52, "Fed healthcare"),
        ("Other Corp", "commence CMS integration QA remote", 48, 52, "fhir"),
    ],
)
def test_estimate_ils_table(
    company: str,
    desc: str,
    expect_min: int,
    expect_max: int,
    note_sub: str,
) -> None:
    row = pd.Series({"company": company, "title": "QA Engineer", "description": desc})
    score, note = triage.estimate_ils(row)
    assert expect_min <= score <= expect_max
    assert note_sub.lower() in note.lower()


def test_jd_derived_ils_fallback_bounds() -> None:
    row = pd.Series(
        {
            "company": "Example",
            "title": "Staff QA Engineer",
            "description": "playwright python pytest 5 years",
        }
    )
    score, note = jd_derived_ils_fallback(row, str(row["description"]).lower())
    assert 18 <= score <= 72
    assert "jd_derived_fallback" in note


@pytest.mark.parametrize(
    "status,cold,expected",
    [
        ("cold", 45, 45),
        ("warm", 45, 35),
        ("strong", 45, 25),
        ("unknown", 45, 45),
    ],
)
def test_ils_floor_for_referral(status: str, cold: int, expected: int) -> None:
    assert triage.ils_floor_for(status, cold) == expected


def test_score_company_override_flat() -> None:
    ov = {"kind": "flat", "score": 55, "note": "fixture"}
    assert score_company_override(ov, company_lower="acme", jd_text="") == (55, "fixture")


def test_load_company_overrides_includes_bundled_example() -> None:
    ovs = load_company_overrides()
    assert "westinghouse" in ovs
    assert ovs["westinghouse"].get("kind") == "nuclear_travel"


def test_triage_review_company_reads_profile_after_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import profile_loader as pl

    test_profile = str(_REPO / "config" / "profile.test.yaml")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "review_companies: [newco]\n"
        f"paths:\n"
        f"  skip_companies: {_REPO / 'config/skip_companies.test.txt'}\n"
        f"  application_index: {_REPO / 'config/application_index.html.example'}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("QA_JOB_PROFILE", str(profile_path))
    pl.reload_profile()

    assert triage._is_review_company("NewCo Inc") is True
    assert triage._is_review_company("Anthropic") is False

    monkeypatch.setenv("QA_JOB_PROFILE", test_profile)
    pl.reload_profile()


def test_reload_runtime_config_picks_up_referral_status_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import profile_loader as pl

    ref_file = tmp_path / "referral_status.txt"
    ref_file.write_text("acme corp,warm\n", encoding="utf-8")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        f"referrals:\n  status_file: {ref_file}\n"
        f"paths:\n"
        f"  skip_companies: {_REPO / 'config/skip_companies.test.txt'}\n"
        f"  application_index: {_REPO / 'config/application_index.html.example'}\n",
        encoding="utf-8",
    )
    test_profile = str(_REPO / "config" / "profile.test.yaml")

    try:
        monkeypatch.setenv("QA_JOB_PROFILE", str(profile_path))
        triage.reload_runtime_config()
        assert triage.referral_status_for("Acme Corp LLC") == "warm"

        ref_file.write_text("acme corp,strong\n", encoding="utf-8")
        triage.reload_runtime_config()
        assert triage.referral_status_for("Acme Corp LLC") == "strong"
    finally:
        monkeypatch.setenv("QA_JOB_PROFILE", test_profile)
        pl.reload_profile()
        triage.reload_runtime_config()

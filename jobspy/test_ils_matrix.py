"""Tests for ils_matrix overrides and travel penalty bands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "jobspy"))

import ils_matrix as im  # noqa: E402
import profile_loader as pl  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_matrix_cache() -> None:
    im.load_ils_matrix.cache_clear()
    pl.get_profile.cache_clear()
    yield
    im.load_ils_matrix.cache_clear()
    pl.get_profile.cache_clear()


def test_load_company_overrides_includes_bundled_example() -> None:
    overrides = im.load_company_overrides()

    assert "westinghouse" in overrides
    assert overrides["westinghouse"]["kind"] == "nuclear_travel"


def test_load_company_overrides_user_json_overrides_example(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_file = tmp_path / "company_ils_overrides.json"
    user_file.write_text(
        json.dumps({"westinghouse": {"kind": "flat", "score": 99, "note": "user wins"}}),
        encoding="utf-8",
    )
    profile = pl.get_profile()
    profile["ils"] = dict(profile.get("ils") or {})
    profile["ils"]["company_overrides_file"] = str(user_file)
    monkeypatch.setattr(im, "get_profile", lambda: profile)

    overrides = im.load_company_overrides()

    assert overrides["westinghouse"]["score"] == 99


@pytest.mark.parametrize(
    "desc,expect_penalty_min",
    [
        ("Requires travel 30-40% for client visits.", 20),
        ("Up to 15% travel.", 0),
        ("", 0),
    ],
)
def test_compute_travel_penalty_bands(desc: str, expect_penalty_min: int) -> None:
    penalty, _tag = im.compute_travel_penalty(desc.lower())

    assert penalty >= expect_penalty_min


@pytest.mark.parametrize(
    "kind,override,company,jd,expected_score,expected_note_part",
    [
        (
            "flat",
            {"kind": "flat", "score": 61, "note": "fixture flat"},
            "acme",
            "",
            61,
            "fixture flat",
        ),
        (
            "nuclear_travel",
            {
                "kind": "nuclear_travel",
                "base_score": 42,
                "min_score": 12,
                "note": "nuclear",
            },
            "westinghouse",
            "travel 35% required",
            22,
            "travel_penalty",
        ),
        (
            "jd_comp_band",
            {
                "kind": "jd_comp_band",
                "low_band_patterns": ["85,000"],
                "low_score": 41,
                "low_note": "low band",
                "default_score": 44,
                "default_note": "default",
            },
            "conduent",
            "salary range $85,000 - $95,000",
            41,
            "low band",
        ),
    ],
)
def test_score_company_override_kinds(
    kind: str,
    override: dict,
    company: str,
    jd: str,
    expected_score: int,
    expected_note_part: str,
) -> None:
    result = im.score_company_override(
        override,
        company_lower=company,
        jd_text=jd.lower(),
    )

    assert result is not None
    score, note = result
    assert score == expected_score
    assert expected_note_part in note


def test_jd_derived_ils_fallback_clamps_to_matrix_bounds() -> None:
    row = pd.Series(
        {
            "company": "Example Co",
            "title": "Staff QA Engineer",
            "description": "playwright python pytest 5 years remote US",
        }
    )
    score, note = im.jd_derived_ils_fallback(row, str(row["description"]).lower())

    matrix = im.load_ils_matrix()
    fb = matrix.get("fallback") or {}
    score_min = int(fb.get("score_min", 18))
    score_max = int(fb.get("score_max", 72))

    assert score_min <= score <= score_max
    assert note.startswith("jd_derived_fallback(")

"""Tests for configure_profile.py helpers and profile roundtrip."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import configure_profile as cp  # noqa: E402


@pytest.fixture
def tmp_profile(tmp_path: Path) -> Path:
    src = _REPO / "config" / "profile.example.yaml"
    dest = tmp_path / "profile.yaml"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def test_parse_comma_list_preserves_internal_spaces() -> None:
    assert cp._parse_comma_list("rest api, github actions, east atlanta") == [
        "rest api",
        "github actions",
        "east atlanta",
    ]


def test_remote_preference_validation_rejects_invalid() -> None:
    inputs = iter(["bogus", "hybrid_home_metro"])
    result = cp._prompt_remote_preference("fully_remote", stdin=lambda _: next(inputs))
    assert result == "hybrid_home_metro"


def test_remote_preference_pick_by_number() -> None:
    result = cp._prompt_remote_preference("fully_remote", stdin=lambda _: "2")
    assert result == "hybrid_home_metro"


def test_remote_preference_enter_keeps_current() -> None:
    assert cp._prompt_remote_preference("any_us_remote", stdin=lambda _: "") == "any_us_remote"


def test_resolve_choice_remote_by_number() -> None:
    assert cp._resolve_choice("3", cp.REMOTE_PREFERENCE_OPTIONS) == "any_us_remote"


def test_resolve_choice_tracks_multi() -> None:
    assert cp._resolve_choice("1, 2", cp.TRACK_OPTIONS, allow_multi=True) == ["A", "B"]


def test_print_remote_preference_menu_includes_all_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cp._print_choice_menu(
        "remote_preference",
        cp.REMOTE_PREFERENCE_OPTIONS,
        current="hybrid_home_metro",
    )
    out = capsys.readouterr().out
    assert "fully_remote" in out
    assert "hybrid_home_metro (current)" in out
    assert "any_us_remote" in out
    assert "1)" in out and "2)" in out and "3)" in out


def test_yaml_roundtrip_preserves_structure(tmp_profile: Path) -> None:
    data = cp._load_yaml(tmp_profile)
    data["owner"] = "Test User"
    data["home_metro"]["zip_anchor"] = "30317"
    cp._save_yaml(tmp_profile, data)
    reloaded = cp._load_yaml(tmp_profile)
    assert reloaded["owner"] == "Test User"
    assert reloaded["home_metro"]["zip_anchor"] == "30317"
    assert isinstance(reloaded["prescreen"]["stack_keywords"], list)


def test_configure_profile_data_mocked_prompts(tmp_profile: Path) -> None:
    data = cp._load_yaml(tmp_profile)
    lines = [
        "",  # owner keep
        "",  # remote keep
        "Portland metro",  # name
        "97209",  # zip
        "portland, beaverton",  # place_names
        "",  # silent_office_hubs keep
        "",  # min_ceiling keep
        "",  # min_floor keep
        "",  # hourly keep
        "",  # gate2 keep
        "playwright, python",  # stack
        "A",  # tracks
    ]
    it = iter(lines)

    def fake_input(_: str) -> str:
        return next(it)

    updated = cp.configure_profile_data(data, stdin=fake_input, interactive=True)
    assert updated["home_metro"]["name"] == "Portland metro"
    assert updated["home_metro"]["zip_anchor"] == "97209"
    assert "portland" in updated["home_metro"]["place_names"]
    assert updated["prescreen"]["stack_keywords"] == ["playwright", "python"]
    assert updated["tracks"]["enable"] == ["A"]


def test_append_skip_companies(tmp_path: Path) -> None:
    skip = tmp_path / "skip.txt"
    skip.write_text("# header\nexisting-corp\n", encoding="utf-8")
    cp._append_skip_companies(
        skip,
        [],
        stdin=lambda _: "New-Corp, another-corp",
        interactive=True,
    )
    text = skip.read_text(encoding="utf-8")
    assert "new-corp" in text
    assert "another-corp" in text
    assert "existing-corp" in text


def test_run_configure_non_interactive(tmp_profile: Path) -> None:
    out = cp.run_configure(tmp_profile, interactive=False)
    assert out == tmp_profile
    assert yaml.safe_load(tmp_profile.read_text(encoding="utf-8"))["owner"] == "Your Name"


def test_example_profile_has_atlanta_defaults_not_portland() -> None:
    data = cp._load_yaml(_REPO / "config" / "profile.example.yaml")
    assert "Atlanta" in str(data["home_metro"]["name"])
    assert data["home_metro"]["zip_anchor"] == "30317"


def test_fixture_profile_stays_portland() -> None:
    data = cp._load_yaml(_REPO / "config" / "profile.test.yaml")
    assert "portland" in str(data["home_metro"]["name"]).lower()
    assert "atlanta" not in str(data).lower()

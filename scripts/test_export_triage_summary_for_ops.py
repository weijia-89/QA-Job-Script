"""Tests for export_triage_summary_for_ops rollup path defaults."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "jobspy"))
sys.path.insert(0, str(_REPO / "scripts"))


@pytest.fixture
def rollup_dir(tmp_path: Path) -> Path:
    return tmp_path / "custom_rollups"


def test_rollup_dir_defaults_from_profile_ops_rollup_dir(
    rollup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import export_triage_summary_for_ops as export_mod

    triage_csv = _REPO / "jobspy" / "results" / "triage_latest_ops.csv"
    sample_df = pd.DataFrame(
        {
            "triage_verdict": ["apply", "skip", "review"],
            "company": ["Acme", "Beta", "Gamma"],
            "title": ["QA Engineer"] * 3,
            "job_url": ["https://example.com/1"] * 3,
        }
    )

    import profile_loader

    monkeypatch.setattr(profile_loader, "ops_rollup_dir", lambda: rollup_dir)
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(return_value=subprocess.CompletedProcess([], 0)),
    )
    monkeypatch.setattr(pd, "read_csv", lambda _path: sample_df.copy())

    argv = [
        "export_triage_summary_for_ops.py",
        "--append-rollup-auto",
        "--quiet",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    export_mod.main()

    expected_rollup = rollup_dir / f"{date.today().isoformat()}.md"
    assert expected_rollup.is_file()
    content = expected_rollup.read_text(encoding="utf-8")
    assert "## Morning triage (auto)" in content
    assert "apply=1" in content


def test_dump_json_writes_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import export_triage_summary_for_ops as export_mod

    out_json = tmp_path / "summary.json"
    sample_df = pd.DataFrame({"triage_verdict": ["apply"], "company": ["Acme"]})

    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(return_value=subprocess.CompletedProcess([], 0)),
    )
    monkeypatch.setattr(pd, "read_csv", lambda _path: sample_df.copy())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_triage_summary_for_ops.py",
            "--dump-json",
            str(out_json),
            "--quiet",
        ],
    )

    export_mod.main()

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["counts"]["apply"] == 1
    assert payload["date_iso"] == date.today().isoformat()

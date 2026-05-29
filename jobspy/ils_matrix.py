"""
Configurable ILS fallback matrix (JD-derived estimate).

Full JFS (job-fit score) and manual ILS research sessions are out of scope.
This module implements the formula layer only — see docs/ILS_MATRIX.md.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("PyYAML required: pip install pyyaml") from exc

from profile_loader import get_profile, ils_settings, repo_root

_REPO = repo_root()
_EXAMPLE_MATRIX = _REPO / "config" / "ils_matrix.example.yaml"
_LOCAL_MATRIX = _REPO / "config" / "ils_matrix.yaml"


def _resolve_matrix_path() -> Path:
    env = os.environ.get("QA_JOB_ILS_MATRIX")
    if env:
        p = Path(os.path.expanduser(env)).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"ILS matrix not found: {p}")
        return p
    ils = ils_settings()
    if ils.get("matrix_file") and os.path.isfile(ils["matrix_file"]):
        return Path(ils["matrix_file"])
    if _LOCAL_MATRIX.is_file():
        return _LOCAL_MATRIX.resolve()
    if _EXAMPLE_MATRIX.is_file():
        return _EXAMPLE_MATRIX.resolve()
    raise FileNotFoundError(
        f"No ILS matrix found. Copy {_EXAMPLE_MATRIX.name} to {_LOCAL_MATRIX.name}."
    )


@lru_cache(maxsize=1)
def load_ils_matrix() -> dict[str, Any]:
    path = _resolve_matrix_path()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"ILS matrix root must be a mapping: {path}")
    if path.name.endswith(".example.yaml"):
        print(
            "[ils] Using config/ils_matrix.example.yaml — "
            "copy to config/ils_matrix.yaml to customize."
        )
    data["_meta"] = {"path": str(path)}
    return data


def compute_travel_penalty(d: str) -> tuple[int, str]:
    """Map stated travel % to ILS deduction (0–28). See docs/ILS_MATRIX.md."""
    if not d:
        return 0, ""

    hi = 0
    tag = ""

    for m in re.finditer(
        r"(?:travel|require\s+you\s+to\s+travel)[^.]{0,55}?(\d{1,2})\s*[-–]\s*(\d{1,2})\s*%",
        d,
        re.I,
    ):
        hi = max(hi, int(m.group(1)), int(m.group(2)))
        tag = re.sub(r"\s+", " ", m.group(0))[:56]

    if hi == 0:
        m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*%\s*travel", d, re.I)
        if m:
            hi = max(int(m.group(1)), int(m.group(2)))
            tag = re.sub(r"\s+", " ", m.group(0))[:56]

    if hi == 0:
        m = re.search(r"up\s+to\s+(\d{1,2})\s*%\s*travel", d, re.I)
        if m:
            hi = int(m.group(1))
            tag = m.group(0)[:56]

    if hi == 0:
        m = re.search(r"\btravel\s+(?:of\s+|up\s+to\s+)?(\d{1,2})\s*%", d, re.I)
        if m:
            hi = int(m.group(1))
            tag = m.group(0)[:56]

    if hi <= 0:
        return 0, ""

    matrix = load_ils_matrix()
    bands = (matrix.get("travel_penalty") or {}).get("bands") or [
        {"min_percent": 50, "penalty": 28},
        {"min_percent": 40, "penalty": 22},
        {"min_percent": 30, "penalty": 20},
        {"min_percent": 20, "penalty": 12},
        {"min_percent": 11, "penalty": 7},
    ]
    for band in sorted(bands, key=lambda b: int(b["min_percent"]), reverse=True):
        if hi >= int(band["min_percent"]):
            return int(band["penalty"]), tag
    return 0, tag


def _parse_overrides_file(path: Path) -> dict[str, dict]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        k: v for k, v in raw.items()
        if not str(k).startswith("_") and isinstance(v, dict)
    }


def load_company_overrides() -> dict[str, dict]:
    """Per-company override entries; gitignored JSON overrides bundled example."""
    ils = ils_settings()
    path = ils.get("company_overrides_file")
    merged: dict[str, dict] = {}
    example = _REPO / "config" / "company_ils_overrides.example.json"
    if example.is_file():
        merged.update(_parse_overrides_file(example))
    if path and os.path.isfile(path):
        merged.update(_parse_overrides_file(Path(path)))
    return merged


def score_company_override(
    ov: dict[str, Any],
    *,
    company_lower: str,
    jd_text: str,
) -> tuple[int, str] | None:
    """Apply one override dict; return None if override does not match this row."""
    kind = str(ov.get("kind") or "flat").lower()
    d = jd_text

    if kind == "flat":
        if "score" not in ov:
            return None
        return int(ov["score"]), str(ov.get("note", ""))

    if kind == "nuclear_travel":
        base = int(ov.get("base_score", 42))
        floor = int(ov.get("min_score", 12))
        tp, _ = compute_travel_penalty(d)
        note = f"{ov.get('note', 'nuclear supplier QA')}; travel_penalty={tp}"
        return max(floor, base - tp), note

    if kind == "jd_comp_band":
        for pat in ov.get("low_band_patterns") or []:
            pat_s = str(pat)
            if pat_s in d or pat_s.replace(",", "") in d.replace("-", ""):
                return int(ov["low_score"]), str(ov.get("low_note", ""))
        return int(ov["default_score"]), str(ov.get("default_note", ""))

    if kind == "company_or_jd_head":
        head_n = int(ov.get("jd_head_chars", 400))
        jd_kw = str(ov.get("jd_keyword") or "")
        if jd_kw and jd_kw in d[:head_n]:
            return int(ov["score"]), str(ov.get("note", ""))
        if ov.get("match_company_substring") and str(ov["match_company_substring"]) in company_lower:
            return int(ov["score"]), str(ov.get("note", ""))
        return None

    return None


def reload_ils_matrix() -> dict[str, Any]:
    load_ils_matrix.cache_clear()
    return load_ils_matrix()


def _d1_points(matrix: dict[str, Any], d: str) -> int:
    cfg = matrix.get("dimensions", {}).get("d1_stack_match", {})
    tools = cfg.get("tools") or []
    hits = sum(1 for t in tools if str(t).lower() in d)
    base = int(cfg.get("base_points", 5))
    per = int(cfg.get("points_per_tool_hit", 2))
    cap = int(cfg.get("max_points", 25))
    return min(cap, base + hits * per)


def _d2_points(matrix: dict[str, Any], d: str, title: str) -> int:
    cfg = matrix.get("dimensions", {}).get("d2_experience", {})
    d2 = int(cfg.get("default_points", 14))
    blob = d + " " + title
    for tier in cfg.get("year_tiers") or []:
        pat = tier.get("pattern")
        if pat and re.search(pat, blob, re.I):
            d2 = int(tier.get("points", d2))
            break
    if re.search(r"\b(?:phd|master'?s)\s+(?:degree\s+)?required\b", d):
        d2 -= int(cfg.get("degree_required_penalty", 3))
    return max(0, d2)


def _d3_points(matrix: dict[str, Any], cs: str, d: str) -> int:
    cfg = matrix.get("dimensions", {}).get("d3_domain_bridge", {})
    d3 = int(cfg.get("default_points", 12))
    for kw in cfg.get("staffing_company_keywords") or []:
        if kw in cs:
            d3 -= int(cfg.get("staffing_company_penalty", 5))
            break
    head = d[: int(cfg.get("staffing_jd_scan_chars", 2500))]
    for kw in cfg.get("staffing_jd_keywords") or []:
        if kw in head:
            d3 -= int(cfg.get("staffing_jd_penalty", 3))
            break
    for kw in cfg.get("nuclear_keywords") or []:
        if kw in d:
            d3 = min(d3, int(cfg.get("nuclear_cap", 7)))
            break
    gig_head = d[: int(cfg.get("gig_work_scan_chars", 1200))]
    for kw in cfg.get("gig_work_keywords") or []:
        if kw in gig_head:
            d3 -= int(cfg.get("gig_work_penalty", 4))
            break
    return max(0, d3)


def jd_derived_ils_fallback(
    row: pd.Series,
    d: str,
    matrix: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Lightweight D1–D5-ish score from JD body (configurable matrix)."""
    matrix = matrix or load_ils_matrix()
    cs = str(row.get("company") or "").lower()
    title = str(row.get("title") or "").lower()

    dims = matrix.get("dimensions", {})
    d1 = _d1_points(matrix, d)
    d2 = _d2_points(matrix, d, title)
    d3 = _d3_points(matrix, cs, d)
    d4 = int(dims.get("d4_application_method", {}).get("default_points", 7))
    d5 = int(dims.get("d5_portfolio", {}).get("default_points", 7))

    tp, travel_tag = compute_travel_penalty(d)
    raw = d1 + d2 + d3 + d4 + d5 - tp

    fb = matrix.get("fallback") or {}
    if "contract" in d[:900] and "w2" not in d[:900]:
        raw -= int(fb.get("contract_without_w2_penalty", 4))

    score_min = int(fb.get("score_min", 18))
    score_max = int(fb.get("score_max", 72))
    score = int(max(score_min, min(score_max, raw)))
    bits = [f"d1≈{d1}", f"d2≈{d2}", f"d3≈{d3}", f"travel−{tp}"]
    if travel_tag:
        bits.append(f"({travel_tag})")
    return score, "jd_derived_fallback(" + "; ".join(bits) + ")"

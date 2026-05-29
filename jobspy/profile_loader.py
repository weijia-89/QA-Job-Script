"""
Load user job-search profile YAML (config/profile.yaml).

Resolution order:
  1. QA_JOB_PROFILE environment variable
  2. config/profile.yaml (gitignored — copy from config/profile.example.yaml)
  3. config/profile.example.yaml (warning printed)

Set QA_JOB_PROFILE in tests or CI to pin a fixture profile.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("PyYAML required: pip install pyyaml") from exc

from paths import CONFIG_DIR, REPO_ROOT  # noqa: E402

_REPO_ROOT = REPO_ROOT
_CONFIG_DIR = CONFIG_DIR
_DEFAULT_PROFILE = _CONFIG_DIR / "profile.example.yaml"
_LOCAL_PROFILE = _CONFIG_DIR / "profile.yaml"


def _expand_path(raw: str, base: Path) -> str:
    expanded = os.path.expanduser(raw)
    path = Path(expanded)
    if not path.is_absolute():
        path = (base / path).resolve()
    return str(path)


def _resolve_profile_path() -> tuple[Path, bool]:
    """Return (path, is_local_copy)."""
    env = os.environ.get("QA_JOB_PROFILE") or os.environ.get("JOB_SEARCH_PROFILE")
    if env:
        p = Path(os.path.expanduser(env)).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Profile not found: {p}")
        return p, p == _LOCAL_PROFILE
    if _LOCAL_PROFILE.is_file():
        return _LOCAL_PROFILE.resolve(), True
    if _DEFAULT_PROFILE.is_file():
        return _DEFAULT_PROFILE.resolve(), False
    raise FileNotFoundError(
        f"No profile found. Copy {_DEFAULT_PROFILE.name} to {_LOCAL_PROFILE.name} "
        "or set QA_JOB_PROFILE."
    )


def _place_names_to_regex(place_names: list[str]) -> re.Pattern[str]:
    """Build case-insensitive substring regex from human place names."""
    parts: list[str] = []
    for name in place_names:
        token = str(name).strip().lower()
        if not token:
            continue
        escaped = re.escape(token).replace(r"\ ", r"\s+")
        parts.append(escaped)
    if not parts:
        parts = [r"__no_places_configured__"]
    return re.compile(rf"\b(?:{'|'.join(parts)})\b", re.IGNORECASE)


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Profile root must be a mapping: {path}")
    return data


@lru_cache(maxsize=1)
def get_profile() -> dict[str, Any]:
    path, is_local = _resolve_profile_path()
    data = _load_yaml(path)
    profile_dir = path.parent

    if not is_local and path.name.endswith(".example.yaml"):
        print(
            "[profile] Using config/profile.example.yaml — "
            f"copy to config/profile.yaml and customize ({_LOCAL_PROFILE.name})."
        )

    referrals = dict(data.get("referrals") or {})
    if referrals.get("status_file"):
        referrals["status_file"] = _expand_path(str(referrals["status_file"]), _REPO_ROOT)
    data["referrals"] = referrals

    paths = dict(data.get("paths") or {})
    for key in ("skip_companies", "application_index", "results_dir", "ops_rollup_dir"):
        if paths.get(key):
            # Paths in profile YAML are repo-root-relative (not profile_dir/config/…).
            paths[key] = _expand_path(str(paths[key]), _REPO_ROOT)
    data["paths"] = paths

    ils = dict(data.get("ils") or {})
    if ils.get("matrix_file"):
        ils["matrix_file"] = _expand_path(str(ils["matrix_file"]), _REPO_ROOT)
    if ils.get("company_overrides_file"):
        ils["company_overrides_file"] = _expand_path(
            str(ils["company_overrides_file"]), _REPO_ROOT
        )
    data["ils"] = ils

    home = dict(data.get("home_metro") or {})
    place_names = list(home.get("place_names") or [])
    data["_compiled"] = {
        "home_metro_re": _place_names_to_regex(place_names),
        "silent_office_hubs_re": _place_names_to_regex(
            list(data.get("silent_office_hubs") or [])
        ),
    }
    data["_meta"] = {"path": str(path), "profile_dir": str(profile_dir)}
    return data


def reload_profile() -> dict[str, Any]:
    get_profile.cache_clear()
    return get_profile()


def remote_preference() -> str:
    return str(get_profile().get("remote_preference") or "hybrid_home_metro")


def home_metro_regex() -> re.Pattern[str]:
    return get_profile()["_compiled"]["home_metro_re"]


def silent_office_hubs_regex() -> re.Pattern[str]:
    return get_profile()["_compiled"]["silent_office_hubs_re"]


def comp_settings() -> dict[str, int]:
    comp = get_profile().get("comp") or {}
    return {
        "min_ceiling_usd": int(comp.get("min_ceiling_usd", 130_000)),
        "min_floor_usd": int(comp.get("min_floor_usd", 110_000)),
        "hourly_annual_floor_usd": int(
            comp.get("hourly_annual_floor_usd", comp.get("min_floor_usd", 110_000))
        ),
        "gate2_floor_usd": int(comp.get("gate2_floor_usd", 145_000)),
    }


def prescreen_stack_keywords() -> frozenset[str]:
    ps = get_profile().get("prescreen") or {}
    kws = ps.get("stack_keywords")
    if not kws:
        return _DEFAULT_STACK_KEYWORDS
    return frozenset(str(k).lower() for k in kws)


def prescreen_priority_limits() -> dict[str, int]:
    ps = get_profile().get("prescreen") or {}
    pr = ps.get("priority") or {}
    return {
        "max_years_high": int(pr.get("max_years_high", 7)),
        "max_years_mod": int(pr.get("max_years_mod", 8)),
        "max_years_low": int(pr.get("max_years_low", 8)),
    }


def ils_settings() -> dict[str, Any]:
    return dict(get_profile().get("ils") or {})


def referral_status_path() -> str:
    ref = get_profile().get("referrals") or {}
    return str(ref.get("status_file") or (_REPO_ROOT / "applications" / "referral_status.txt"))


def verified_remote_employers() -> tuple[str, ...]:
    items = get_profile().get("verified_remote_employers") or []
    return tuple(str(x).lower() for x in items)


def review_company_substrings() -> tuple[str, ...]:
    items = get_profile().get("review_companies") or ["crowdstrike", "ifit solutions"]
    return tuple(str(x).lower() for x in items)


def enabled_tracks() -> frozenset[str]:
    """Enabled scrape tracks from profile ``tracks.enable`` (uppercase IDs)."""
    tracks = get_profile().get("tracks") or {}
    raw = tracks.get("enable")
    if raw is None:
        return frozenset({"A", "B", "C", "G", "R", "GH", "L", "AS"})
    out = {str(x).strip().upper() for x in raw if str(x).strip()}
    return frozenset(out) if out else frozenset({"A"})


def ops_rollup_dir() -> Path:
    paths = get_profile().get("paths") or {}
    raw = paths.get("ops_rollup_dir")
    if raw:
        p = Path(_expand_path(str(raw), _REPO_ROOT))
        return p
    return _REPO_ROOT / "jobspy" / "results" / "ops_rollups"


def repo_root() -> Path:
    return _REPO_ROOT


_DEFAULT_STACK_KEYWORDS = frozenset([
    "playwright", "python", "pytest", "typescript", "javascript",
    "github actions", "ci/cd", "cicd", "rest api", "graphql",
    "selenium", "docker", "sql", "golang",
    "llm eval", "llm evaluation", "ai evaluation", "model evaluation",
    "test automation", "shift-left", "shift left",
    "api testing", "automated testing", "e2e testing",
])

#!/usr/bin/env python3
"""
Interactive profile setup for QA-Job-Script onboarding.

Walks through docs/your-profile.md onboarding fields, optional skip list and ILS
customization, and writes config/profile.yaml via PyYAML.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml") from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = REPO_ROOT / "config" / "profile.yaml"
DEFAULT_SKIP_FILE = REPO_ROOT / "applications" / "skip_companies.txt"
DEFAULT_ILS_MATRIX = REPO_ROOT / "config" / "ils_matrix.yaml"
ILS_EXAMPLE = REPO_ROOT / "config" / "ils_matrix.example.yaml"

REMOTE_PREFERENCES = ("fully_remote", "hybrid_home_metro", "any_us_remote")
TRACK_ID_RE = re.compile(r"^[A-Z0-9]{1,3}$")


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Profile root must be a mapping: {path}")
    return data


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def _get_nested(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _set_nested(data: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    cur = data
    for key in keys[:-1]:
        nxt = cur.setdefault(key, {})
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _format_current(value: Any) -> str:
    if value is None:
        return "(not set)"
    if isinstance(value, list):
        if not value:
            return "(empty list)"
        return ", ".join(str(v) for v in value)
    return str(value)


def _parse_comma_list(raw: str) -> list[str]:
    """Split comma-separated input; preserves spaces inside each item."""
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _prompt_line(
    label: str,
    description: str,
    current: Any,
    example: str,
    *,
    stdin: Callable[[str], str] | None = None,
) -> str | None:
    read = stdin or input
    print()
    print(f"  {label}")
    print(f"    What: {description}")
    print(f"    Current: {_format_current(current)}")
    print(f"    Example: {example}")
    entered = read("  Enter value (Enter = keep current): ").strip()
    if not entered:
        return None
    return entered


def _prompt_remote_preference(
    current: str,
    *,
    stdin: Callable[[str], str] | None = None,
) -> str:
    read = stdin or input
    allowed = ", ".join(REMOTE_PREFERENCES)
    while True:
        entered = _prompt_line(
            "remote_preference",
            "How strictly to filter work arrangement (US-focused).",
            current,
            "hybrid_home_metro",
            stdin=read,
        )
        if entered is None:
            return current
        choice = entered.strip().lower()
        if choice in REMOTE_PREFERENCES:
            return choice
        print(f"    Invalid — choose one of: {allowed}")


def _prompt_int_field(
    label: str,
    description: str,
    current: int,
    example: str,
    *,
    stdin: Callable[[str], str] | None = None,
) -> int:
    read = stdin or input
    while True:
        entered = _prompt_line(label, description, current, example, stdin=read)
        if entered is None:
            return current
        try:
            return int(entered.replace(",", "").strip())
        except ValueError:
            print("    Invalid — enter a whole number (USD).")


def _prompt_list_field(
    label: str,
    description: str,
    current: list[str],
    example: str,
    *,
    stdin: Callable[[str], str] | None = None,
    lowercase: bool = False,
) -> list[str]:
    read = stdin or input
    entered = _prompt_line(
        label,
        description + " Comma-separated on one line.",
        current,
        example,
        stdin=read,
    )
    if entered is None:
        return list(current)
    items = _parse_comma_list(entered)
    if lowercase:
        items = [x.lower() for x in items]
    return items


def _prompt_tracks(
    current: list[str],
    *,
    stdin: Callable[[str], str] | None = None,
) -> list[str]:
    read = stdin or input
    entered = _prompt_line(
        "tracks.enable",
        "Which scrape channels to run (see docs/your-profile.md).",
        [str(x).upper() for x in current],
        "A or A, B",
        stdin=read,
    )
    if entered is None:
        return list(current)
    raw = entered.replace("[", "").replace("]", "")
    tokens = [t.strip().upper() for t in re.split(r"[\s,]+", raw) if t.strip()]
    valid = [t for t in tokens if TRACK_ID_RE.match(t)]
    if not valid:
        print("    No valid track IDs — keeping current.")
        return list(current)
    return valid


def configure_profile_data(
    data: dict[str, Any],
    *,
    stdin: Callable[[str], str] | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    if not interactive:
        return data

    read = stdin or input
    print()
    print("=== Interactive profile setup ===")
    print("Press Enter on any prompt to keep the current value.")
    print("List fields accept comma-separated values (spaces inside items are OK).")

    owner = _prompt_line(
        "owner",
        "Display name for scrape logs and triage output — not sent to job boards.",
        data.get("owner"),
        "jordan-qa",
        stdin=read,
    )
    if owner is not None:
        data["owner"] = owner

    data["remote_preference"] = _prompt_remote_preference(
        str(data.get("remote_preference") or "hybrid_home_metro"),
        stdin=read,
    )

    home = dict(data.get("home_metro") or {})
    name = _prompt_line(
        "home_metro.name",
        "Display label for logs only (not used for location matching).",
        home.get("name"),
        "Atlanta, GA",
        stdin=read,
    )
    if name is not None:
        home["name"] = name

    zip_anchor = _prompt_line(
        "home_metro.zip_anchor",
        "Home-area US ZIP (5 digits) — anchor for hybrid commute reference.",
        home.get("zip_anchor"),
        "30317",
        stdin=read,
    )
    if zip_anchor is not None:
        home["zip_anchor"] = zip_anchor

    place_names = _prompt_list_field(
        "home_metro.place_names",
        "City/suburb strings matched as substrings in job location and JD text.",
        list(home.get("place_names") or []),
        "atlanta, decatur, sandy springs",
        stdin=read,
        lowercase=True,
    )
    home["place_names"] = place_names
    data["home_metro"] = home

    hubs = _prompt_list_field(
        "silent_office_hubs",
        "US office cities that imply onsite when the JD is silent on remote.",
        list(data.get("silent_office_hubs") or []),
        "seattle, san francisco, new york",
        stdin=read,
        lowercase=True,
    )
    data["silent_office_hubs"] = hubs

    comp = dict(data.get("comp") or {})
    comp["min_ceiling_usd"] = _prompt_int_field(
        "comp.min_ceiling_usd",
        "Scraper L1 pass if posted max salary is at or above this (USD annual).",
        int(comp.get("min_ceiling_usd", 130_000)),
        "130000",
        stdin=read,
    )
    comp["min_floor_usd"] = _prompt_int_field(
        "comp.min_floor_usd",
        "Scraper L1 pass if posted min salary is at or above this (USD annual).",
        int(comp.get("min_floor_usd", 110_000)),
        "110000",
        stdin=read,
    )
    comp["hourly_annual_floor_usd"] = _prompt_int_field(
        "comp.hourly_annual_floor_usd",
        "Hourly postings annualized at 2080 hrs/yr must meet this floor.",
        int(comp.get("hourly_annual_floor_usd", 110_000)),
        "110000",
        stdin=read,
    )
    comp["gate2_floor_usd"] = _prompt_int_field(
        "comp.gate2_floor_usd",
        "Minimum salary for the gate2_at_145k CSV column (floor from this key).",
        int(comp.get("gate2_floor_usd", 145_000)),
        "145000",
        stdin=read,
    )
    data["comp"] = comp

    prescreen = dict(data.get("prescreen") or {})
    stack = _prompt_list_field(
        "prescreen.stack_keywords",
        "Words/phrases counted in the JD for stack_hits.",
        list(prescreen.get("stack_keywords") or []),
        "playwright, python, pytest, typescript",
        stdin=read,
        lowercase=True,
    )
    prescreen["stack_keywords"] = stack
    data["prescreen"] = prescreen

    tracks = dict(data.get("tracks") or {})
    enable = _prompt_tracks(list(tracks.get("enable") or ["A"]), stdin=read)
    tracks["enable"] = enable
    data["tracks"] = tracks

    return data


def _append_skip_companies(
    skip_path: Path,
    slugs: list[str],
    *,
    stdin: Callable[[str], str] | None = None,
    interactive: bool = True,
) -> None:
    if not interactive:
        return
    read = stdin or input
    print()
    print("=== Skip companies (optional) ===")
    entered = read(
        "  Add companies to skip now? Comma-separated slugs, or Enter to skip: "
    ).strip()
    if not entered:
        return
    new_slugs = [s.strip().lower() for s in _parse_comma_list(entered) if s.strip()]
    if not new_slugs:
        return
    skip_path.parent.mkdir(parents=True, exist_ok=True)
    existing = skip_path.read_text(encoding="utf-8") if skip_path.is_file() else ""
    lines = existing.splitlines()
    present = {ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")}
    with open(skip_path, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        for slug in new_slugs:
            if slug not in present:
                f.write(f"{slug}\n")
                present.add(slug)
    print(f"  Updated {skip_path}")


def _maybe_customize_ils(
    ils_path: Path,
    *,
    stdin: Callable[[str], str] | None = None,
    interactive: bool = True,
) -> None:
    if not interactive:
        return
    read = stdin or input
    if not ils_path.is_file():
        if ILS_EXAMPLE.is_file():
            ils_path.parent.mkdir(parents=True, exist_ok=True)
            ils_path.write_text(ILS_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  Copied {ILS_EXAMPLE.name} -> {ils_path}")
        return
    ans = read("  Customize ILS matrix now? (y/N): ").strip().lower()
    if ans not in ("y", "yes"):
        return
    ed = __import__("os").environ.get("EDITOR") or __import__("os").environ.get("VISUAL")
    if ed:
        import subprocess

        subprocess.run([ed, str(ils_path)], check=False)
    else:
        print(f"  Edit manually: {ils_path}")
        print("  Guide: docs/ils-matrix.md")


def run_configure(
    profile_path: Path,
    *,
    skip_path: Path | None = None,
    ils_path: Path | None = None,
    stdin: Callable[[str], str] | None = None,
    interactive: bool = True,
) -> Path:
    if not profile_path.is_file():
        raise FileNotFoundError(
            f"Profile not found: {profile_path}. "
            "Run onboarding first to copy config/profile.example.yaml."
        )

    data = _load_yaml(profile_path)
    data = configure_profile_data(data, stdin=stdin, interactive=interactive)
    _save_yaml(profile_path, data)
    print(f"\n  Saved {profile_path}")

    skip = skip_path or DEFAULT_SKIP_FILE
    _append_skip_companies(skip, [], stdin=stdin, interactive=interactive)

    ils = ils_path or DEFAULT_ILS_MATRIX
    _maybe_customize_ils(ils, stdin=stdin, interactive=interactive)

    return profile_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive QA-Job-Script profile setup.")
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Path to config/profile.yaml (default: repo config/profile.yaml)",
    )
    parser.add_argument(
        "--skip-file",
        type=Path,
        default=None,
        help="Path to skip_companies.txt (default: applications/skip_companies.txt)",
    )
    parser.add_argument(
        "--ils-matrix",
        type=Path,
        default=None,
        help="Path to ils_matrix.yaml (default: config/ils_matrix.yaml)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Load and re-save profile without prompts (validation smoke).",
    )
    args = parser.parse_args(argv)

    try:
        run_configure(
            args.profile.resolve(),
            skip_path=args.skip_file.resolve() if args.skip_file else None,
            ils_path=args.ils_matrix.resolve() if args.ils_matrix else None,
            interactive=not args.non_interactive and sys.stdin.isatty(),
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Check whether onboarding pip install can be skipped.

Reads requirements.txt constraints and verifies installed distributions
in the active Python (venv if activated).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"

# pip distribution name -> import module (for secondary import check)
IMPORT_MODULES: dict[str, str] = {
    "pandas": "pandas",
    "requests": "requests",
    "python-jobspy": "jobspy",
    "pytest": "pytest",
    "pyyaml": "yaml",
}

REQ_LINE = re.compile(
    r"^([a-zA-Z0-9_.-]+)\s*(?:([><=!]+)\s*([\d.]+))?\s*(?:,\s*([><=!]+)\s*([\d.]+))?"
)


@dataclass(frozen=True)
class Requirement:
    name: str
    lower: str | None = None
    upper: str | None = None

    @classmethod
    def parse_line(cls, line: str) -> Requirement | None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None
        m = REQ_LINE.match(stripped)
        if not m:
            return None
        name = m.group(1).lower()
        lower = upper = None
        if m.group(2) and m.group(3):
            op, ver = m.group(2), m.group(3)
            if op in (">=", ">"):
                lower = ver
            elif op in ("==",):
                lower = upper = ver
        if m.group(4) and m.group(5):
            op2, ver2 = m.group(4), m.group(5)
            if op2 == "<":
                upper = ver2
        return cls(name=name, lower=lower, upper=upper)


def load_requirements(path: Path = REQUIREMENTS) -> list[Requirement]:
    reqs: list[Requirement] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        req = Requirement.parse_line(line)
        if req:
            reqs.append(req)
    return reqs


def _version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for seg in re.split(r"[.\-+]", v.split("+")[0]):
        m = re.match(r"^(\d+)", seg)
        parts.append(int(m.group(1)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _version_satisfies(installed: str, lower: str | None, upper: str | None) -> bool:
    iv = _version_tuple(installed)
    if lower is not None and iv < _version_tuple(lower):
        return False
    if upper is not None and iv >= _version_tuple(upper):
        return False
    return True


def _importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _installed_version(dist_name: str) -> str | None:
    try:
        return version(dist_name)
    except PackageNotFoundError:
        # PyYAML publishes as PyYAML on PyPI but pip show accepts pyyaml
        if dist_name == "pyyaml":
            try:
                return version("PyYAML")
            except PackageNotFoundError:
                return None
        return None


@dataclass
class DepStatus:
    name: str
    ok: bool
    detail: str


def assess_requirements(
    reqs: list[Requirement] | None = None,
) -> tuple[bool, list[DepStatus]]:
    if reqs is None:
        reqs = load_requirements()
    statuses: list[DepStatus] = []
    for req in reqs:
        dist = req.name
        mod = IMPORT_MODULES.get(dist, dist.replace("-", "_"))
        ver = _installed_version(dist)
        if ver is None:
            statuses.append(DepStatus(dist, False, "not installed"))
            continue
        if not _version_satisfies(ver, req.lower, req.upper):
            want = []
            if req.lower:
                want.append(f">={req.lower}")
            if req.upper:
                want.append(f"<{req.upper}")
            statuses.append(
                DepStatus(dist, False, f"installed {ver}, need {', '.join(want)}")
            )
            continue
        if mod and not _importable(mod):
            statuses.append(DepStatus(dist, False, f"installed {ver} but import {mod} failed"))
            continue
        statuses.append(DepStatus(dist, True, ver))
    return all(s.ok for s in statuses), statuses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check onboarding Python dependencies.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Exit 0 if all requirements satisfied, 1 otherwise (no output).",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        default=REQUIREMENTS,
        help="Path to requirements.txt",
    )
    args = parser.parse_args(argv)

    reqs = load_requirements(args.requirements)
    ok, statuses = assess_requirements(reqs)

    if args.check_only:
        return 0 if ok else 1

    if ok:
        print("Dependencies already installed — skipping pip install")
        return 0

    missing = [s for s in statuses if not s.ok]
    print("Some dependencies missing or outdated — running pip install:")
    for s in missing:
        print(f"  - {s.name}: {s.detail}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

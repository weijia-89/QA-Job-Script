"""Shared company skip resolution for L1 scrape and L2 triage.

Single source for normalize_company_key, skip-key expansion, prefix-safe matching,
and staffing-wrapper hint cross-checks. See docs/application_index_company_extraction_contract.md §10.
"""

from __future__ import annotations

import html as _html
import logging
import os
import re
from typing import Iterable

from index_companies import load_applied_companies_from_path

_NON_ALNUM_RE = re.compile(r'[^a-z0-9]')
_OUTER_PAREN_RE = re.compile(r'\s*\([^)]*\)')
_MIN_SKIP_KEY_LEN = 4

_SKIP_COMPANY_SUFFIXES = frozenset({
    'inc', 'llc', 'ltd', 'corp', 'corporation', 'co', 'company', 'companies',
    'group', 'holdings', 'holding', 'technologies', 'technology', 'tech',
    'labs', 'lab', 'ai', 'health', 'healthcare', 'software', 'systems',
    'solutions', 'services', 'service', 'global', 'international', 'usa', 'us',
    'io', 'llp', 'plc', 'gmbh', 'sa', 'limited', 'digital',
})

_SKIP_TITLE_SUBSTRINGS = frozenset({
    'becton dickinson',
})

_DEFAULT_RESOLVER: SkipResolver | None = None


def normalize_company_key(s: object) -> str:
    """Canonical company key: html-unescape → lowercase → strip non-alphanumeric."""
    if s is None:
        return ''
    return _NON_ALNUM_RE.sub('', _html.unescape(str(s)).lower())


def skip_key_variants(raw: object) -> list[str]:
    """1–2 normalized skip-key variants for a raw skip-list entry."""
    primary = normalize_company_key(raw)
    if '(' not in str(raw or ''):
        return [primary] if primary else []
    stripped = _OUTER_PAREN_RE.sub('', str(raw)).strip()
    secondary = normalize_company_key(stripped)
    variants: list[str] = []
    if primary:
        variants.append(primary)
    if secondary and secondary != primary:
        variants.append(secondary)
    return variants


def build_normalized_skip_keys(raw_skip_companies: Iterable[str]) -> frozenset[str]:
    """Normalized skip keys from raw slugs; drops keys shorter than _MIN_SKIP_KEY_LEN."""
    out: set[str] = set()
    dropped: list[str] = []
    for raw in raw_skip_companies:
        any_emitted = False
        for k in skip_key_variants(raw):
            if len(k) >= _MIN_SKIP_KEY_LEN:
                out.add(k)
                any_emitted = True
        if not any_emitted and normalize_company_key(raw):
            dropped.append(str(raw))
    if dropped:
        logging.warning(
            'skip_companies: dropping %d short keys (<%d chars after normalize): %s',
            len(dropped), _MIN_SKIP_KEY_LEN, sorted(dropped),
        )
    return frozenset(out)


def company_matches_skip_key(company_norm: str, skip_key: str) -> bool:
    """Match company to one skip key without substring false positives."""
    if not company_norm or not skip_key:
        return False
    if company_norm == skip_key:
        return True
    if not company_norm.startswith(skip_key):
        return False
    suffix = company_norm[len(skip_key):]
    if suffix == '':
        return True
    if len(skip_key) >= 10:
        return True
    return suffix in _SKIP_COMPANY_SUFFIXES


def _load_skip_companies_from_file(path: str) -> set[str]:
    out: set[str] = set()
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.split('#', 1)[0].strip()
            if line:
                out.add(line.lower())
    return out


def _load_pre_assessment_skip_slugs(applications_dir: str) -> set[str]:
    out: set[str] = set()
    if not os.path.isdir(applications_dir):
        return out
    verdict_re = re.compile(r'##\s+Verdict:.*\bSKIP\b', re.IGNORECASE)
    for entry in os.listdir(applications_dir):
        pa_path = os.path.join(applications_dir, entry, 'pre_assessment.md')
        if not os.path.isfile(pa_path):
            continue
        try:
            with open(pa_path, encoding='utf-8') as f:
                head = f.read(12_000)
        except OSError as exc:
            logging.warning('pre_assessment skip scan failed for %s: %s', pa_path, exc)
            continue
        if not verdict_re.search(head):
            continue
        slug = entry.strip().lower()
        if slug:
            out.add(slug.replace('_', ' '))
            out.add(slug.replace('_', ''))
    return out


class SkipResolver:
    """Mutable raw skip set + lazily rebuilt normalized keys."""

    def __init__(self, raw_skip: set[str]) -> None:
        self.raw_skip_companies = raw_skip
        self._normalized_skip: frozenset[str] | None = None

    def invalidate_cache(self) -> None:
        self._normalized_skip = None

    def normalized_skip_keys(self) -> frozenset[str]:
        if self._normalized_skip is None:
            self._normalized_skip = build_normalized_skip_keys(self.raw_skip_companies)
        return self._normalized_skip

    def skip_company_match_key(self, name: object) -> str | None:
        n = normalize_company_key(name)
        if not n:
            return None
        for k in self.normalized_skip_keys():
            if company_matches_skip_key(n, k):
                return k
        return None

    def is_skip_company(self, name: object) -> bool:
        return self.skip_company_match_key(name) is not None

    def is_skip_title_company_signal(self, title: str) -> bool:
        t = str(title).lower()
        return any(s in t for s in _SKIP_TITLE_SUBSTRINGS)

    def hint_matches_skip_company_bidirectional(self, hint: object) -> bool:
        """Wrapper-hint cross-check: prefix match in either direction (hints ≥4 chars)."""
        hint_norm = normalize_company_key(hint)
        if not hint_norm or len(hint_norm) < _MIN_SKIP_KEY_LEN:
            return False
        for skip_key in self.normalized_skip_keys():
            if hint_norm.startswith(skip_key) or skip_key.startswith(hint_norm):
                return True
        return False

    @classmethod
    def bootstrap(
        cls,
        applications_dir: str,
        skip_companies_txt: str,
        index_html_path: str,
    ) -> SkipResolver:
        try:
            raw = _load_skip_companies_from_file(skip_companies_txt)
            print(
                f'[skip-list] Loaded {len(raw)} entries from '
                f'{os.path.basename(skip_companies_txt)}'
            )
        except OSError as exc:
            logging.warning(
                'skip_companies file unavailable (%s); using empty file-backed set',
                exc,
            )
            print(
                f'[skip-list] WARNING: {exc}; no file-backed skip entries '
                f'(create {os.path.basename(skip_companies_txt)} from '
                'config/skip_companies.txt.example)'
            )
            raw = set()

        applied = load_applied_companies_from_path(index_html_path)
        raw.update(applied)
        if applied:
            print(f'[auto-skip] Added {len(applied)} applied companies from index.')

        pre_skip = _load_pre_assessment_skip_slugs(applications_dir)
        raw.update(pre_skip)
        if pre_skip:
            print(f'[auto-skip] Added {len(pre_skip)} pre-assessment SKIP slugs.')

        return cls(raw)


def install_resolver(resolver: SkipResolver) -> None:
    global _DEFAULT_RESOLVER
    _DEFAULT_RESOLVER = resolver


def default_bootstrap_paths() -> tuple[str, str, str]:
    """(applications_dir, skip_companies_txt, application_index_html)."""
    applications_dir = os.path.dirname(os.path.abspath(__file__))
    return (
        applications_dir,
        os.path.join(applications_dir, 'skip_companies.txt'),
        os.path.join(applications_dir, 'application_index.html'),
    )


def get_resolver() -> SkipResolver:
    if _DEFAULT_RESOLVER is None:
        install_resolver(SkipResolver.bootstrap(*default_bootstrap_paths()))
    return _DEFAULT_RESOLVER


def invalidate_default_cache() -> None:
    get_resolver().invalidate_cache()


def rebootstrap_from_profile(applications_dir: str | None = None) -> SkipResolver:
    """Re-read skip sources from the active profile (paths.skip_companies, etc.)."""
    import sys
    from pathlib import Path

    _jobspy_dir = Path(__file__).resolve().parent.parent / "jobspy"
    if str(_jobspy_dir) not in sys.path:
        sys.path.insert(0, str(_jobspy_dir))
    from profile_loader import get_profile

    profile = get_profile()
    paths = profile.get('paths') or {}
    default_apps, default_skip, default_index = default_bootstrap_paths()
    apps = applications_dir or default_apps
    skip_txt = str(paths.get('skip_companies') or default_skip)
    index_html = str(paths.get('application_index') or default_index)
    resolver = SkipResolver.bootstrap(apps, skip_txt, index_html)
    install_resolver(resolver)
    return resolver

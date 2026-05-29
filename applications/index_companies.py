from __future__ import annotations

"""Parse application_index.html for company tokens (auto-skip / dedupe)."""

INDEX_COMPANIES_CONTRACT_VERSION = "1.4.0"
INDEX_COMPANIES_ROLE_PATTERN = r'class="role"[^>]*>(?:<[^>]+>)?([^—–<]+)'
INDEX_COMPANIES_SKIP_ITEM_PATTERN = (
    r'class="skip-item"[^>]*>\s*<strong[^>]*>([^<—–]+?)(?:\s*</strong>)'
)

import logging
import re
from pathlib import Path

_ROLE_COMPANY = re.compile(INDEX_COMPANIES_ROLE_PATTERN)
_SKIP_ITEM_COMPANY = re.compile(INDEX_COMPANIES_SKIP_ITEM_PATTERN)


def load_applied_companies(html: str) -> set[str]:
    """Company slugs from role rows and skip-item entries in the index HTML."""
    found: set[str] = set()
    for m in _ROLE_COMPANY.finditer(html):
        company = m.group(1).strip().rstrip(",").lower()
        if len(company) > 2:
            found.add(company)
    for m in _SKIP_ITEM_COMPANY.finditer(html):
        company = m.group(1).strip().rstrip(",").lower()
        if len(company) > 2:
            found.add(company)
    return found


def load_applied_companies_from_path(path: str | Path) -> set[str]:
    try:
        html = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return set()
    except OSError as exc:
        logging.warning("auto-skip parse: %s", exc)
        return set()
    return load_applied_companies(html)

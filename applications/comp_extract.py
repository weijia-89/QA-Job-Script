"""
comp_extract.py — USD compensation extraction from ATS pages and JD text.

Used by prescreen (JobSpy CSV), triage_jobspy_csv, and manual pre_assessment
Gate 2 blocks. (Upstream repos may also wire a one-off JD capture script.) Does not overwrite JobSpy structured
min_amount/max_amount; adds parallel jd_comp_* columns for audit.

Tier tags for assessments:
  T1 — employer ATS header (Rippling/Lever/Greenhouse band near title)
  T2 — same employer JD body (salary section in description)
  T3 — aggregator / inferred only
"""

from __future__ import annotations

import html as html_module
import json
import math
import re
from dataclasses import dataclass
from typing import Optional

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CompResult:
    min_usd: Optional[int]
    max_usd: Optional[int]
    midpoint_usd: Optional[int]
    currency: Optional[str]
    interval: str  # annual | hourly | unknown
    disclosed: bool
    source: str  # structured_csv | ats_header | jd_body | competitive_only | none
    snippet: str
    confidence: str  # high | medium | low

    def gate2_at_floor(self, floor_usd: int = 145_000) -> str:
        """PASS | MARGINAL | FAIL | UNKNOWN — career-helper Gate 2 label."""
        return gate2_label(self.min_usd, self.max_usd, floor_usd)


# ── Patterns ──────────────────────────────────────────────────────────────────

_DASH = r"[-–—‒to]+"

_COMPETITIVE_ONLY = re.compile(
    r"\bcompetitive\s+(?:salary|compensation|pay|benefits|package)\b",
    re.IGNORECASE,
)

_NON_USD_NEAR = re.compile(
    r"(?:[£€₹]|\b(?:gbp|eur|inr|cad|mxn)\b)",
    re.IGNORECASE,
)

# Rippling / modern ATS header: $130,000 ‒ $160,000 Annually
_RANGE_FULL = re.compile(
    rf"\$\s*(\d{{1,3}}(?:,\d{{3}})+|\d{{2,3}}(?:\.\d+)?)\s*(?:k|K)?\s*{_DASH}\s*"
    rf"\$\s*(\d{{1,3}}(?:,\d{{3}})+|\d{{2,3}}(?:\.\d+)?)\s*(?:k|K)?"
    r"(?:\s*(?:annually|per\s+year|a\s+year|yearly|/yr))?",
    re.IGNORECASE,
)

# $130k-$160k, 130K to 160K, $112.5k-$168.75k
_RANGE_K = re.compile(
    rf"\$?\s*(\d{{2,3}}(?:\.\d+)?)\s*k\s*{_DASH}\s*\$?\s*(\d{{2,3}}(?:\.\d+)?)\s*k\b",
    re.IGNORECASE,
)

# Up to $180,000 / salary up to $200k
_SINGLE_HIGH = re.compile(
    r"(?:up\s+to|maximum|max\.?|ceiling)\s+(?:of\s+)?"
    r"\$?\s*(\d{1,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?)\s*(?:k|K)?",
    re.IGNORECASE,
)

# Standalone $145,000 when labeled salary/compensation nearby
_SINGLE_LABELED = re.compile(
    r"(?:base\s+)?(?:salary|compensation|pay)\s*(?:range)?\s*[:#]?\s*"
    r"\$?\s*(\d{1,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?)\s*(?:k|K)?\b",
    re.IGNORECASE,
)

_HOURLY_MARK = re.compile(r"(?:/|\s)(?:hour|hr)\b|hourly", re.IGNORECASE)

_HOURS_PER_YEAR = 2080

# Rippling / HiringThing embedded pay (HTML-entity or plain JSON)
_RIPPLING_SALARY_AMOUNT = re.compile(
    r'(?:min|max)Salary(?:&quot;|")?\s*:\s*\{(?:&quot;|")amount(?:&quot;|")?\s*:\s*'
    r'(?:&quot;|")(\d+(?:\.\d+)?)',
    re.IGNORECASE,
)

_LD_JSON_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _is_empty(val: object) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def _parse_amount(token: str, *, has_k_suffix: bool = False) -> Optional[int]:
    """Parse '$130,000', '130', '112.5' with optional k context → annual USD int."""
    if not token:
        return None
    t = token.strip().replace(",", "")
    try:
        val = float(t)
    except ValueError:
        return None
    if has_k_suffix or (val < 1000 and "." in t):
        # 112.5k → 112500; 160k → 160000
        if val < 1000:
            return int(round(val * 1000))
    if val < 1000 and not has_k_suffix and "." not in t:
        # bare 130 in k-range regex handled by caller
        return int(val * 1000) if val < 500 else int(val)
    if val < 10000:
        return int(round(val * 1000)) if val < 500 else int(val)
    return int(round(val))


def _midpoint(lo: Optional[int], hi: Optional[int]) -> Optional[int]:
    if lo is not None and hi is not None:
        return (lo + hi) // 2
    return lo if lo is not None else hi


def _snippet(text: str, start: int, end: int, *, max_len: int = 120) -> str:
    s = text[max(0, start) : min(len(text), end)].strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _foreign_pay_without_usd(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 80) : min(len(text), end + 80)]
    if not _NON_USD_NEAR.search(window):
        return False
    return "$" not in window and "usd" not in window.lower()


def _match_range(
    text: str,
    pattern: re.Pattern[str],
    *,
    use_k: bool,
    source: str,
    interval: str = "annual",
) -> Optional[CompResult]:
    for m in pattern.finditer(text):
        if _foreign_pay_without_usd(text, m.start(), m.end()):
            continue
        lo = _parse_amount(m.group(1), has_k_suffix=use_k)
        hi = _parse_amount(m.group(2), has_k_suffix=use_k)
        if lo is None or hi is None:
            continue
        if lo > hi:
            lo, hi = hi, lo
        local_interval = interval
        tail = text[m.end() : m.end() + 40]
        if _HOURLY_MARK.search(text[max(0, m.start() - 30) : m.end() + 40]):
            local_interval = "hourly"
            lo = int(lo * _HOURS_PER_YEAR) if lo < 500 else lo
            hi = int(hi * _HOURS_PER_YEAR) if hi < 500 else hi
        return CompResult(
            min_usd=lo,
            max_usd=hi,
            midpoint_usd=_midpoint(lo, hi),
            currency="USD",
            interval=local_interval,
            disclosed=True,
            source=source,
            snippet=_snippet(text, m.start(), m.end()),
            confidence="high" if source == "ats_header" else "medium",
        )
    return None


def extract_comp_from_html(html: str) -> Optional[CompResult]:
    """Rippling JSON embed, schema.org JobPosting baseSalary, then visible salary div."""
    if not html:
        return None

    unescaped = html_module.unescape(html)
    mins: list[float] = []
    maxs: list[float] = []
    for m in _RIPPLING_SALARY_AMOUNT.finditer(html):
        val = float(m.group(1))
        label = m.group(0).lower()
        if label.startswith("min"):
            mins.append(val)
        else:
            maxs.append(val)
    for m in _RIPPLING_SALARY_AMOUNT.finditer(unescaped):
        val = float(m.group(1))
        label = m.group(0).lower()
        if label.startswith("min"):
            mins.append(val)
        else:
            maxs.append(val)

    if mins or maxs:
        lo = int(min(mins)) if mins else None
        hi = int(max(maxs)) if maxs else None
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        return CompResult(
            min_usd=lo,
            max_usd=hi,
            midpoint_usd=_midpoint(lo, hi),
            currency="USD",
            interval="annual",
            disclosed=True,
            source="ats_header",
            snippet=f"Rippling embed min={lo} max={hi}",
            confidence="high",
        )

    for block in _LD_JSON_BLOCK.finditer(html):
        try:
            data = json.loads(block.group(1).strip())
        except json.JSONDecodeError:
            continue
        base = data.get("baseSalary") if isinstance(data, dict) else None
        if not isinstance(base, dict):
            continue
        val = base.get("value") if isinstance(base.get("value"), dict) else base
        if not isinstance(val, dict):
            continue
        lo = val.get("minValue") or val.get("value")
        hi = val.get("maxValue") or lo
        try:
            lo_i = int(float(lo)) if lo is not None else None
            hi_i = int(float(hi)) if hi is not None else None
        except (TypeError, ValueError):
            continue
        if lo_i or hi_i:
            return CompResult(
                min_usd=lo_i,
                max_usd=hi_i,
                midpoint_usd=_midpoint(lo_i, hi_i),
                currency="USD",
                interval="annual",
                disclosed=True,
                source="ats_header",
                snippet="schema.org baseSalary",
                confidence="high",
            )

    return None


def extract_comp_from_text(
    text: str,
    *,
    header_chars: int = 2500,
) -> CompResult:
    """
    Extract USD annual compensation from JD HTML/plain text.
    Prefers the first ~header_chars (ATS title band) over body.
    """
    if not text or not str(text).strip():
        return _empty("none")

    raw = str(text)
    if "<" in raw[:800] or "minSalary" in raw or "maxSalary" in raw:
        html_hit = extract_comp_from_html(raw)
        if html_hit is not None and html_hit.disclosed:
            return html_hit

    # Strip common HTML tags for matching
    cleaned = re.sub(r"<[^>]+>", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned)

    if _COMPETITIVE_ONLY.search(cleaned[:8000]) and not _RANGE_FULL.search(
        cleaned[:header_chars]
    ):
        if not _RANGE_K.search(cleaned[:header_chars]):
            return CompResult(
                min_usd=None,
                max_usd=None,
                midpoint_usd=None,
                currency=None,
                interval="unknown",
                disclosed=False,
                source="competitive_only",
                snippet="competitive salary",
                confidence="low",
            )

    header = cleaned[:header_chars]
    for pat, use_k in ((_RANGE_FULL, False), (_RANGE_K, True)):
        hit = _match_range(header, pat, use_k=use_k, source="ats_header")
        if hit:
            return hit

    body = cleaned[header_chars:]
    for pat, use_k in ((_RANGE_FULL, False), (_RANGE_K, True)):
        hit = _match_range(body, pat, use_k=use_k, source="jd_body")
        if hit:
            return hit

    m = _SINGLE_HIGH.search(cleaned)
    if m and not _foreign_pay_without_usd(cleaned, m.start(), m.end()):
        hi = _parse_amount(m.group(1), has_k_suffix=bool(re.search(r"k\b", m.group(0), re.I)))
        if hi:
            return CompResult(
                min_usd=None,
                max_usd=hi,
                midpoint_usd=hi,
                currency="USD",
                interval="annual",
                disclosed=True,
                source="jd_body",
                snippet=_snippet(cleaned, m.start(), m.end()),
                confidence="medium",
            )

    m = _SINGLE_LABELED.search(cleaned)
    if m and not _foreign_pay_without_usd(cleaned, m.start(), m.end()):
        val = _parse_amount(m.group(1), has_k_suffix=bool(re.search(r"k\b", m.group(0), re.I)))
        if val:
            return CompResult(
                min_usd=val,
                max_usd=val,
                midpoint_usd=val,
                currency="USD",
                interval="annual",
                disclosed=True,
                source="jd_body",
                snippet=_snippet(cleaned, m.start(), m.end()),
                confidence="medium",
            )

    return _empty("none")


def _empty(source: str) -> CompResult:
    return CompResult(
        min_usd=None,
        max_usd=None,
        midpoint_usd=None,
        currency=None,
        interval="unknown",
        disclosed=False,
        source=source,
        snippet="",
        confidence="low",
    )


def _coerce_structured(val: object) -> Optional[int]:
    if _is_empty(val):
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return int(round(f))
    except (TypeError, ValueError):
        return None


def merge_comp(
    structured_min: object,
    structured_max: object,
    jd: CompResult,
) -> CompResult:
    """
    Prefer JobSpy/Lever structured min/max when present; else JD extraction.
    """
    smin = _coerce_structured(structured_min)
    smax = _coerce_structured(structured_max)
    if smin is not None or smax is not None:
        return CompResult(
            min_usd=smin,
            max_usd=smax,
            midpoint_usd=_midpoint(smin, smax),
            currency="USD",
            interval="annual",
            disclosed=True,
            source="structured_csv",
            snippet=jd.snippet or f"structured {smin}-{smax}",
            confidence="high",
        )
    return jd


def effective_comp_min(result: CompResult) -> Optional[int]:
    return result.min_usd if result.min_usd is not None else result.max_usd


def effective_comp_max(result: CompResult) -> Optional[int]:
    return result.max_usd if result.max_usd is not None else result.min_usd


def gate2_label(
    min_usd: Optional[int],
    max_usd: Optional[int],
    floor_usd: int = 145_000,
) -> str:
    """PASS | MARGINAL | FAIL | UNKNOWN."""
    if min_usd is None and max_usd is None:
        return "UNKNOWN"
    lo = min_usd if min_usd is not None else max_usd
    hi = max_usd if max_usd is not None else min_usd
    if hi is not None and hi < floor_usd:
        return "FAIL"
    if lo is not None and lo >= floor_usd:
        return "PASS"
    if lo is not None and lo < floor_usd and hi is not None and hi >= floor_usd:
        return "MARGINAL"
    return "UNKNOWN"


def format_comp_markdown(result: CompResult, *, tier_tag: str = "T1") -> str:
    """Markdown block for jd.md ## Comp section."""
    if not result.disclosed:
        return (
            "## Comp\n\n"
            "**Disclosed:** No — competitive / undisclosed only. "
            f"`[Gate 2: UNKNOWN]`\n"
        )
    lo, hi = result.min_usd, result.max_usd
    if lo is not None and hi is not None and lo != hi:
        band = f"**${lo:,} – ${hi:,}** annually"
    elif lo is not None:
        band = f"**${lo:,}** annually"
    elif hi is not None:
        band = f"up to **${hi:,}** annually"
    else:
        band = "*(parsed but empty)*"
    mid = result.midpoint_usd
    mid_s = f" (mid **${mid:,}**)" if mid is not None and lo != hi else ""
    g2 = result.gate2_at_floor()
    src = result.source.replace("_", " ")
    snip = f' — snippet: "{result.snippet}"' if result.snippet else ""
    return (
        "## Comp\n\n"
        f"**Posted band:** {band}{mid_s}  \n"
        f"**Source:** {src} `{tier_tag}`{snip}  \n"
        f"**Gate 2 (@ $145k floor):** **{g2}**\n"
    )


def source_tier_tag(result: CompResult) -> str:
    if result.source == "structured_csv":
        return "T1"
    if result.source == "ats_header":
        return "T1"
    if result.source == "jd_body":
        return "T2"
    if result.source == "competitive_only":
        return "T2"
    return "T3"


def patch_jd_comp_section(path: str, result: CompResult) -> bool:
    """Replace or append ## Comp in jd.md. Returns True if file changed."""
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8")
    block = format_comp_markdown(result, tier_tag=source_tier_tag(result))
    if "## Comp" in text:
        new_text = re.sub(
            r"## Comp\b.*?(?=\n## |\Z)",
            block.rstrip() + "\n\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
    else:
        new_text = text.rstrip() + "\n\n" + block
    if new_text == text:
        return False
    p.write_text(new_text, encoding="utf-8")
    return True


def row_comp_result(
    description: object,
    min_amount: object = None,
    max_amount: object = None,
) -> CompResult:
    jd = extract_comp_from_text("" if _is_empty(description) else str(description))
    return merge_comp(min_amount, max_amount, jd)


def add_comp_columns(df, gate2_floor_usd: int | None = None):  # pandas DataFrame
    """Add jd_comp_* and gate2_at_145k columns; does not alter min_amount/max_amount."""
    import pandas as pd

    floor = gate2_floor_usd if gate2_floor_usd is not None else 145_000

    df = df.copy()
    if "description" not in df.columns:
        df["jd_comp_disclosed"] = False
        df["gate2_at_145k"] = "UNKNOWN"
        return df

    comp_rows = df.apply(
        lambda r: row_comp_result(
            r.get("description"),
            r.get("min_amount") if "min_amount" in df.columns else None,
            r.get("max_amount") if "max_amount" in df.columns else None,
        ),
        axis=1,
    )
    df["jd_comp_min"] = comp_rows.apply(lambda c: c.min_usd)
    df["jd_comp_max"] = comp_rows.apply(lambda c: c.max_usd)
    df["jd_comp_mid"] = comp_rows.apply(lambda c: c.midpoint_usd)
    df["jd_comp_snippet"] = comp_rows.apply(lambda c: c.snippet)
    df["jd_comp_source"] = comp_rows.apply(lambda c: c.source)
    df["jd_comp_disclosed"] = comp_rows.apply(lambda c: c.disclosed)
    df["gate2_at_145k"] = comp_rows.apply(lambda c: c.gate2_at_floor(floor))
    df["effective_comp_min"] = comp_rows.apply(effective_comp_min)
    df["effective_comp_max"] = comp_rows.apply(effective_comp_max)
    return df

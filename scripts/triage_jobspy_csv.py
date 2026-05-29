#!/usr/bin/env python3
"""
Triage JobSpy CSV rows using the same filters as jobspy/run_search_locally.py.

Verdicts:
  skip   — fails any hard gate (same order as the scraper filter pipeline), or post-gates
  review — passes pipeline + post-gates but employer is on manual review tier (CrowdStrike, IFIT)
  apply  — passes pipeline + post-gates and is not on the review tier

Post-gates (default on; see --no-post-gates):
  • Arrangement: skip if JD is not US full-remote as primary mode, or hybrid/office outside
    the Atlanta core metro, or primary office is non-remote (per Wei's latest rule text).
  • ILS: conservative point estimate; skip if < --ils-floor (default 45).

Usage:
  python3 triage_jobspy_csv.py --latest
  python3 triage_jobspy_csv.py /path/to/jobspy_results_YYYYMMDD.csv
  python3 triage_jobspy_csv.py --latest --out jobspy/results/triage_latest.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CAREER_HELP_ROOT = os.path.dirname(_SCRIPT_DIR)
_APPLICATIONS = os.path.join(_CAREER_HELP_ROOT, 'applications')
_JOBSPY_PKG = os.path.join(_CAREER_HELP_ROOT, 'jobspy')
_JOBSPY_DIR = os.path.join(_JOBSPY_PKG, 'results')

sys.path.insert(0, _JOBSPY_PKG)
from profile_loader import (  # noqa: E402
    get_profile,
    home_metro_regex,
    ils_settings,
    referral_status_path,
    reload_profile,
    review_company_substrings,
    verified_remote_employers,
)
from ils_matrix import (  # noqa: E402
    jd_derived_ils_fallback,
    load_company_overrides,
    load_ils_matrix,
    reload_ils_matrix,
    score_company_override,
)

get_profile()
load_ils_matrix()

# Referral-aware ILS floors (Patch 2026-05-15 #4).
#
# Rationale: in the AI-boom application volume era (2025+), cold-apply senior
# tech roles routinely see 1,500-5,000 applicants. ATS auto-filters + 3-10
# sec recruiter scans mean cold-apply odds collapsed faster than referral
# odds — referrals now bypass ~90% of the funnel (LinkedIn 2025 hiring data:
# ~45% of senior tech hires are referrals, up from 30% in 2022). The single
# ILS-floor model under-skipped wheelhouse-miss cold roles and over-skipped
# bridgeable referral-available roles. Tiered floors fix both directions.
#
# Default floor in `--ils-floor` (CLI default 45) is the COLD floor. The
# warm/strong tiers are RELATIVE to the cold floor — passing `--ils-floor 50`
# raises all three floors together.
def _referral_warm_delta() -> int:
    return int(ils_settings().get("referral_warm_delta", -10))


def _referral_strong_delta() -> int:
    return int(ils_settings().get("referral_strong_delta", -20))


def _load_referral_status(path: str) -> dict[str, str]:
    """Load per-company referral status from a plain-text file.

    Format: one entry per line, ``company_substring,status`` where
    ``status`` is ``cold`` (default — no entry needed), ``warm`` (Wei has at
    least one LinkedIn connection at the company), or ``strong`` (Wei knows
    someone on the hiring team / has a likely HM intro path). Lines starting
    with ``#`` are comments; empty lines ignored. Company match is
    case-insensitive substring against the JobSpy ``company`` column.

    Missing file: empty dict (everyone is cold). Malformed lines logged and
    skipped rather than failing the run.
    """
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                # Strip inline comments — common user mistake to write
                # `company,warm   # note` and have the parser treat the entire
                # tail (including the '#' and prose) as the status field.
                # Per the file format, comments are line-level only, but the
                # inline form is intuitive enough to support defensively.
                if '#' in s:
                    s = s.split('#', 1)[0].rstrip()
                    if not s:
                        continue
                if ',' not in s:
                    logging.warning('referral_status.txt:%d malformed (no comma): %r', lineno, s)
                    continue
                company, status = (p.strip() for p in s.split(',', 1))
                status_lc = status.lower()
                if status_lc not in {'cold', 'warm', 'strong'}:
                    logging.warning(
                        'referral_status.txt:%d invalid status %r (use cold/warm/strong)',
                        lineno, status,
                    )
                    continue
                if not company:
                    continue
                out[company.lower()] = status_lc
    except OSError as exc:
        logging.warning('referral_status.txt read failed: %s', exc)
    return out


def _referral_status_path() -> str:
    env = os.environ.get("TRIAGE_REFERRAL_STATUS")
    if env:
        return os.path.expanduser(env)
    return referral_status_path()


_REFERRAL_STATUS: dict[str, str] = _load_referral_status(_referral_status_path())


def referral_status_for(company: object) -> str:
    """Return cold / warm / strong for a JobSpy company string. Default cold."""
    cs = str(company or '').lower()
    if not cs:
        return 'cold'
    # Substring match (not equality) — JobSpy company strings vary
    # ("Reveleer" vs "Reveleer, Inc." vs "Reveleer (via Indeed)").
    for key, status in _REFERRAL_STATUS.items():
        if key in cs:
            return status
    return 'cold'


def ils_floor_for(status: str, cold_floor: int) -> int:
    """Return the ILS floor for a referral status given the cold-tier baseline."""
    if status == 'strong':
        return max(0, cold_floor + _referral_strong_delta())
    if status == 'warm':
        return max(0, cold_floor + _referral_warm_delta())
    return cold_floor


_ILS_OVERRIDES: dict[str, dict] = load_company_overrides()

sys.path.insert(0, _JOBSPY_PKG)
sys.path.insert(0, _APPLICATIONS)
import run_search_locally as rsl  # noqa: E402
from skip_resolver import get_resolver  # noqa: E402

# Phase 4 merge (2026-05-16): import shared domain inference + gate detection
# from the refresh-skill module so both pipelines stay aligned. See
# applications/scripts/refresh_lib/domain_inference.py for canonical rules.
sys.path.insert(0, os.path.join(_APPLICATIONS, 'scripts'))
try:
    from refresh_lib.domain_inference import (  # noqa: E402
        detect_gates as _di_detect_gates,
        estimate_tier_from_domain as _di_estimate_tier,
        infer_domain_from_text as _di_infer_domain,
    )
    _DOMAIN_INFERENCE_AVAILABLE = True
except ImportError as _exc:
    logging.warning('refresh_lib.domain_inference unavailable: %s; phase4 columns will be empty', _exc)
    _DOMAIN_INFERENCE_AVAILABLE = False

_RE_JOBSPY = re.compile(r"^jobspy_results_(\d{8})\.csv$")

# Employers that stay off SKIP_COMPANIES but never auto-classify as "apply".
# Stricter than TITLE_REQUIRED: excludes pure PM/PO tracks that still hit the whitelist.
_QA_PRIMARY_HINTS = (
    "sdet",
    "software engineer in test",
    " set ",
    "quality",
    " qa",
    "qa ",
    " qe",
    "qe ",
    "test automation",
    "automation engineer",
    "evaluation",
    "llm eval",
    "model eval",
    "ai quality",
    "test engineer",
    "testing engineer",
)


def _qa_primary_title(title: str) -> bool:
    t = title.lower()
    return any(h in t for h in _QA_PRIMARY_HINTS)


def _is_review_company(company: object) -> bool:
    n = str(company or "").lower()
    for s in review_company_substrings():
        if s in n:
            return True
    return n.strip() == "ifit"


# ── Staffing-wrapper detection (Patch 2026-05-15 #5) ─────────────────────────
#
# Problem: JobSpy preserves the LinkedIn `company` field, but for staffing-aug
# postings, that field is the staffing firm (DOMA Technologies, KForce, Apex
# Systems, Insight Global, etc.) — NOT the actual employer. The canonical JD
# URL also lives on the actual employer's ATS (paylocity, greenhouse, ashby,
# workday, ICIMS) rather than on LinkedIn. For example: JobSpy returned the
# 2026-05-15 Lead QA role under "DOMA Technologies" with the LinkedIn apply
# URL, but the actual employer is LIVANTA LLC / branded "Commence", and the
# canonical JD is at recruiting.paylocity.com/recruiting/jobs/Details/4145884/
# LIVANTA-LLC/Lead-Quality-Assurance-Engineer.
#
# What this module does:
# 1) Detect when JobSpy `company` matches a known staffing-wrapper substring.
# 2) Extract a best-effort "real employer" hint from the JD body via the
#    `At <Employer>, we…` opening pattern that 95%+ of staffing-aug JDs use.
# 3) Emit two output columns: `apply_url_check_needed` (bool) and
#    `wrapper_employer_hint` (str — may be empty if no hint extractable).
#
# This is a HINT, not a hard skip. The role still flows through normal
# triage; the columns just nudge Wei to find the canonical careers-page URL
# before applying. A future patch could resolve the URL automatically via
# playwright but that's out of scope here.

# Known staffing wrappers (lowercase substring match). Add new entries
# sparingly — false-positives degrade signal quality on direct hires.
_STAFFING_WRAPPERS: tuple[str, ...] = (
    "doma technologies",
    "kforce",
    "apex systems",
    "insight global",
    "robert half",
    "tek systems",
    "tekSystems".lower(),
    "n-ix",                 # staff-aug across LATAM/EU
    "epam",                 # large consultancy with US contracts
    "wissen",
    "infosys",
    "tcs",                  # tata
    "accenture",
    "deloitte",
    "cognizant",
    "capgemini",
)

# Pattern: matches "At Commence, we're…" / "At LIVANTA, our…" / "Join Acme as a…"
# style openings. Anchored to opening 1500 chars to avoid catching company
# names mentioned downstream as customers / partners. Non-greedy capture
# bounded by punctuation. Restrict capture group to letters/digits/space/
# common punctuation to avoid runaway matches.
_BODY_EMPLOYER_HINT = re.compile(
    r"\bAt\s+([A-Z][A-Za-z0-9&'.\-\s]{2,40}?),\s+(?:we|our)\b",
)
_BODY_EMPLOYER_HINT_JOIN = re.compile(
    r"\bJoin\s+([A-Z][A-Za-z0-9&'.\-\s]{2,40}?)\s+as\s+a\b",
)


def is_staffing_wrapper(company: object) -> bool:
    """True if the JobSpy `company` matches a known staffing wrapper."""
    cs = str(company or "").lower()
    if not cs:
        return False
    return any(w in cs for w in _STAFFING_WRAPPERS)


def extract_employer_hint(desc: object) -> str:
    """Best-effort extraction of the real-employer name from a JD body.

    Returns the captured name (preserved casing) or empty string on no match.
    Limited to the first 1500 chars of the body to avoid catching downstream
    mentions of partners / customers. Caller is responsible for confirming
    via the actual careers page; this is a hint only.
    """
    if desc is None or (isinstance(desc, float) and pd.isna(desc)):
        return ""
    s = str(desc)[:1500]
    # Try "At <Employer>, we/our" first (most common JD opener).
    m = _BODY_EMPLOYER_HINT.search(s)
    if m:
        name = m.group(1).strip().rstrip(",")
        # Skip generic non-employer captures.
        if name.lower() not in {"first", "least", "minimum", "this point", "this time"}:
            return name
    # Fall back to "Join <Employer> as a …"
    m = _BODY_EMPLOYER_HINT_JOIN.search(s)
    if m:
        return m.group(1).strip().rstrip(",")
    return ""


def detect_wrapper(company: object, desc: object) -> tuple[bool, str]:
    """Return (is_wrapper, employer_hint).

    - is_wrapper=True when JobSpy `company` matches a known staffing-wrapper
      substring. The hint is best-effort from JD body; may be empty.
    - is_wrapper=False otherwise. We still extract a hint when the JD opens
      with a clear "At <Employer>, we…" pattern AND the captured employer
      name does NOT match the JobSpy company (proxy signal for a wrapper we
      haven't catalogued yet). In that case is_wrapper stays False but the
      hint is surfaced; rule tag downstream is `wrapper_hint_unknown_pattern`.
    """
    if is_staffing_wrapper(company):
        return True, extract_employer_hint(desc)
    # Heuristic for unknown wrappers: JobSpy company and the JD's "At X, we"
    # opener disagree by enough that the role likely isn't directly with the
    # JobSpy company.
    hint = extract_employer_hint(desc)
    if hint:
        company_norm = re.sub(r'[^a-z0-9]', '', str(company or '').lower())
        hint_norm = re.sub(r'[^a-z0-9]', '', hint.lower())
        # Disagreement = neither name is a prefix of the other (covers
        # subsidiaries like "Acme Health" → "Acme" but flags true mismatches).
        if (
            company_norm and hint_norm
            and not company_norm.startswith(hint_norm)
            and not hint_norm.startswith(company_norm)
        ):
            return False, hint
    return False, ""


def _home_metro_blob() -> re.Pattern[str]:
    return home_metro_regex()

# Employee US-remote signals (JD body).
_FULL_REMOTE_US = re.compile(
    r"(?:100%\s*remote|fully\s*remote|completely\s*remote|all[-\s]?remote\b"
    r"|💻\s*remote|#\s*li[-\s]?remote\b|remote\s+work\s*:|"
    r"this\s+is\s+a\s+remote\s+position\b|"
    r"remote\s+position\s+based\s+in\s+the\s+united\s+states|"
    r"flexibility\s+of\s+working\s+from\s+home|"
    r"work\s+from\s+home\s+while)",
    re.IGNORECASE,
)

# Primary office / not-remote-as-default.
_OFFICE_PRIMARY = re.compile(
    r"(?:based\s+at\s+the\s+\w+|full[-\s]?time\s+position\s+based\s+at|"
    r"day\s*1\s+onsite|onsite/hybrid|hybrid\)\s*[–-]\s*fulltime|"
    r"mode\s+of\s+work:\s*\d+\s*days?/\s*week\s+onsite|"
    r"remote\s+work\s+is\s+at\s+the\s+discretion\s+of\s+the\s+manager)",
    re.IGNORECASE,
)


def arrangement_skip(desc: object, loc: object, company: object) -> tuple[bool, str]:
    """
    True + reason if listing fails Wei's remote / hybrid-in-ATL / not-primary-office rules.
    """
    d_raw = "" if desc is None or (isinstance(desc, float) and pd.isna(desc)) else str(desc)
    d = d_raw[:25_000].lower()
    l = "" if loc is None or (isinstance(loc, float) and pd.isna(loc)) else str(loc).lower()
    blob = d + "\n" + l
    cs = str(company or "").lower()

    if "based in mexico" in d or "currently based in mexico" in d:
        return True, "arrangement_non_us_remote"

    # YETI: HQ-primary role even if manager discretion mentions remote.
    if "yeti" in cs or re.search(r"based at the bozeman", d, re.I):
        return True, "arrangement_yeti_bozeman_primary"

    # Scheduled hybrid / onsite days (incl. Wissen-class).
    if re.search(
        r"(?:mode\s+of\s+work:\s*\d+\s*days?/\s*week\s+onsite|"
        r"\d+\s*days?/\s*week\s+onsite|day\s*1\s+onsite|onsite/hybrid)",
        d,
        re.I,
    ):
        return True, "arrangement_hybrid_or_scheduled_onsite"

    if "abbvie" in cs and "within the plant" in d:
        return True, "arrangement_plant_onsite"

    if "tram" in cs and not _FULL_REMOTE_US.search(d):
        return True, "arrangement_tram_no_employee_remote_jd"

    if "quva" in cs and not re.search(
        r"(?:100%\s*remote|fully\s*remote|this\s+is\s+a\s+remote\s+position|"
        r"remote\s+position\s+based\s+in\s+the\s+united\s+states|work\s+from\s+home)",
        d,
        re.I,
    ):
        return True, "arrangement_quva_no_employee_remote_statement"

    # Taulia (SAP group): Wei has direct-verified the role is fully US-remote
    # via Taulia's own careers page (`Location: US, Remote: Yes` in the
    # structured fields), but the LinkedIn JD body that JobSpy pulls only
    # carries the "Remote-friendly environment" benefits-section copy. The
    # pre-2026-05-15 carve-out flagged Taulia as `_remote_friendly_not_
    # guaranteed` which produced a false-positive skip on the otherwise
    # qualifying Principal QE role. Per Wei's allowlist override, bypass
    # arrangement_skip entirely for SAP Taulia. If a new evidence pattern
    # contradicts this (e.g. JD explicitly says hybrid Pleasanton), add a
    # negative carve-out here.
    if any(emp in cs for emp in verified_remote_employers()):
        return False, ""

    # Explicit US employee remote language → pass arrangement.
    if _FULL_REMOTE_US.search(d) or re.search(
        r"remote\s+in\s+[a-z]{2,4}\s+contract", d, re.I
    ):
        return False, ""

    if re.search(r"remote-friendly", d):
        return True, "arrangement_remote_friendly_only"

    if _OFFICE_PRIMARY.search(d):
        return True, "arrangement_primary_office_or_discretionary_remote"

    if re.search(r"\bhybrid\b", d):
        if _home_metro_blob().search(blob):
            return True, "arrangement_hybrid_not_fully_remote_atl"
        return True, "arrangement_hybrid_non_atlanta"

    return False, ""


def _normalize_jd_for_scoring(desc: object) -> str:
    """Undo common LinkedIn/CSV escape noise so regexes match human-readable JDs."""
    if desc is None or (isinstance(desc, float) and pd.isna(desc)):
        return ""
    s = str(desc)[:24_000].lower()
    s = s.replace("\\-", "-").replace("\\.", ".").replace("\\+", "+")
    s = s.replace("\\%", "%")
    s = re.sub(r"\\(?=[%\-+.,:;])", "", s)
    return s


def estimate_ils(row: pd.Series) -> tuple[int, str]:
    """
    Conservative ILS point estimate (0–100 scale per docs/reference-ils-scoring-model.md).
    Not a substitute for a full scored session — used only for the <45 skip gate.

    Lookup order:
      1. config/company_ils_overrides.json (or bundled example) — per-company overrides
         (``kind``: flat, nuclear_travel, jd_comp_band, company_or_jd_head).
      2. jd_derived_ils_fallback — generic D1–D5 formula on the JD body.
    """
    cs = str(row.get("company") or "").lower()
    d = _normalize_jd_for_scoring(row.get("description"))

    for key, ov in _ILS_OVERRIDES.items():
        jd_head = int(ov.get("jd_head_chars", 400))
        jd_kw = str(ov.get("jd_keyword") or "")
        jd_hit = bool(jd_kw and jd_kw in d[:jd_head])
        if key not in cs and not (
            str(ov.get("kind") or "") == "company_or_jd_head" and jd_hit
        ):
            continue
        scored = score_company_override(ov, company_lower=cs, jd_text=d)
        if scored is not None:
            return scored

    return jd_derived_ils_fallback(row, d)


def post_gate_row(
    row: pd.Series,
    *,
    ils_floor: int,
    post_gates: bool,
) -> tuple[str, str, str, str]:
    """
    After pipeline verdict: return (final_verdict, final_rule, ils_str, ils_driver).
    """
    base_v = str(row.get("pipeline_verdict") or "")
    base_rule = str(row.get("pipeline_rule") or "")
    if base_v == "skip" or not post_gates:
        ils, inote = estimate_ils(row)
        return base_v, base_rule, f"{ils}", inote

    desc = row.get("description")
    loc = row.get("location")
    company = row.get("company")

    skip_arr, arr_r = arrangement_skip(desc, loc, company)
    ils, ils_note = estimate_ils(row)
    cs = str(company or "").lower()

    # ── Wei-verified-allowlist override (2026-05-15) ──
    # Some companies have JD-page evidence (from careers site) that contradicts
    # the LinkedIn body — Wei has manually verified them as US-remote /
    # legitimate-employer. Promote to `apply` (bypasses arrangement AND ILS
    # floor). Add to this tuple sparingly; the override skips both gates.
    if any(emp in cs for emp in verified_remote_employers()):
        return "apply", "verified_remote_allowlist", f"{ils}", ils_note

    if skip_arr:
        return "skip", arr_r, f"{ils}", ils_note

    # ── Referral-aware ILS floor (2026-05-15) ──
    # Look up the row's company in referral_status.txt; use a relaxed floor
    # for `warm` / `strong` entries. Default (cold) uses the CLI --ils-floor.
    # The applied floor is embedded in the rule tag so triage CSV consumers
    # can audit which tier fired.
    status = referral_status_for(company)
    effective_floor = ils_floor_for(status, ils_floor)
    if ils < effective_floor:
        if status == 'cold':
            rule = f"ils_below_{effective_floor}"
        else:
            rule = f"ils_below_{effective_floor}_{status}_tier"
        return "skip", rule, f"{ils}", ils_note

    if _is_review_company(str(company or "")):
        return "review", "review_tier_passed_gates", f"{ils}", ils_note

    # Surface the referral status on apply rows so Wei sees it in the triage
    # CSV without having to cross-reference the referral_status.txt file.
    if status == 'cold':
        return "apply", "pipeline_ok_post_gates", f"{ils}", ils_note
    return "apply", f"pipeline_ok_post_gates_{status}_tier", f"{ils}", ils_note


def latest_jobspy_csv(directory: str) -> str:
    paths = []
    for name in os.listdir(directory):
        m = _RE_JOBSPY.match(name)
        if m:
            paths.append(os.path.join(directory, name))
    if not paths:
        raise SystemExit(f"No jobspy_results_YYYYMMDD.csv under {directory}")
    return max(paths, key=lambda p: _RE_JOBSPY.match(os.path.basename(p)).group(1))


def _scalar(val: object) -> object:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return val


def reload_runtime_config() -> None:
    """Reload profile-backed state (referral tiers, ILS matrix/overrides, skip resolver).

    Call at triage startup so edits to profile.yaml, referral_status.txt, skip list,
    or ILS matrix on disk are picked up without requiring a fresh Python import.
    """
    reload_profile()
    global _REFERRAL_STATUS, _ILS_OVERRIDES  # noqa: PLW0603
    _REFERRAL_STATUS = _load_referral_status(_referral_status_path())
    _ILS_OVERRIDES = load_company_overrides()
    reload_ils_matrix()
    rsl.refresh_skip_resolver()


def triage_row(row: pd.Series, *, require_qa_primary: bool) -> tuple[str, str]:
    """
    Return (verdict, rule) where rule is a short machine-readable reason for skip/review.
    """
    company = _scalar(row.get("company"))
    title = _scalar(row.get("title"))
    desc = row.get("description")
    loc = _scalar(row.get("location"))
    mn = row.get("min_amount")
    mx = row.get("max_amount")

    company_s = "" if company is None else str(company)
    title_s = "" if title is None else str(title)
    loc_s = "" if loc is None else str(loc)

    skip = get_resolver()
    if skip.is_skip_company(company_s):
        return "skip", "skip_company"
    # Wrapper-hint cross-check: shared bidirectional skip match (skip_resolver).
    is_wrapper, wrapper_hint = detect_wrapper(company_s, desc)
    if is_wrapper and wrapper_hint and skip.hint_matches_skip_company_bidirectional(wrapper_hint):
        return "skip", "skip_company_via_wrapper_hint"

    fail = rsl.l1_pipeline_fail_rule(company, title, desc, loc, mn, mx)
    if fail:
        return "skip", fail

    if _is_review_company(company_s):
        return "review", "review_tier_employer"

    if require_qa_primary and not _qa_primary_title(title_s):
        return "skip", "not_qa_primary_title"

    return "apply", "pipeline_ok"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "csv_path",
        nargs="?",
        help="Path to jobspy_results_YYYYMMDD.csv (default: --latest)",
    )
    ap.add_argument(
        "--latest",
        action="store_true",
        help=f"Use newest jobspy_results_*.csv under {_JOBSPY_DIR}",
    )
    ap.add_argument(
        "--out",
        metavar="FILE",
        help="Write full triage CSV with verdict + rule columns",
    )
    ap.add_argument(
        "--include-pm-po",
        action="store_true",
        help="Allow Product Owner / TPM-only titles into apply (default: QA-primary titles only)",
    )
    ap.add_argument(
        "--ils-floor",
        type=int,
        default=45,
        metavar="N",
        help="Skip post-gate if conservative ILS estimate is below N (default: 45)",
    )
    ap.add_argument(
        "--no-post-gates",
        action="store_true",
        help="Disable ILS + arrangement post-gates (pipeline only)",
    )
    ap.add_argument(
        "--profile",
        metavar="YAML",
        help="Profile YAML path (default: config/profile.yaml or QA_JOB_PROFILE)",
    )
    args = ap.parse_args()

    if args.profile:
        os.environ["QA_JOB_PROFILE"] = os.path.expanduser(args.profile)
    reload_runtime_config()

    if args.latest and args.csv_path:
        ap.error("Pass either --latest or a csv path, not both")
    if args.latest:
        path = latest_jobspy_csv(_JOBSPY_DIR)
    elif args.csv_path:
        path = os.path.expanduser(args.csv_path)
    else:
        path = latest_jobspy_csv(_JOBSPY_DIR)

    if not os.path.isfile(path):
        raise SystemExit(f"Not a file: {path}")

    df = pd.read_csv(path)
    if "jd_comp_min" not in df.columns:
        sys.path.insert(0, _APPLICATIONS)
        from comp_extract import add_comp_columns  # noqa: E402
        from profile_loader import comp_settings  # noqa: E402

        df = add_comp_columns(df, gate2_floor_usd=comp_settings()["gate2_floor_usd"])
    require_qa = not args.include_pm_po
    pv, pr = [], []
    for _, row in df.iterrows():
        v, ru = triage_row(row, require_qa_primary=require_qa)
        pv.append(v)
        pr.append(ru)
    df = df.copy()
    df["pipeline_verdict"] = pv
    df["pipeline_rule"] = pr

    post_gates = not args.no_post_gates
    fv, fr, ils_es, ils_ns = [], [], [], []
    for _, row in df.iterrows():
        row2 = row.copy()
        row2["pipeline_verdict"] = row["pipeline_verdict"]
        row2["pipeline_rule"] = row["pipeline_rule"]
        a, b, c, d = post_gate_row(
            row2,
            ils_floor=args.ils_floor,
            post_gates=post_gates,
        )
        fv.append(a)
        fr.append(b)
        ils_es.append(c)
        ils_ns.append(d)
    df["triage_verdict"] = fv
    df["triage_rule"] = fr
    df["ils_estimate"] = ils_es
    df["ils_driver"] = ils_ns

    # ── Wrapper / canonical-employer hint columns (Patch 2026-05-15 #5) ──
    # Computed on all rows (not just apply) so the audit trail covers skip
    # rows too — useful for revisiting skipped roles when a wrapper-class
    # signal might have changed.
    wrap_flags: list[bool] = []
    wrap_hints: list[str] = []
    for _, row in df.iterrows():
        is_w, hint = detect_wrapper(row.get("company"), row.get("description"))
        wrap_flags.append(is_w)
        wrap_hints.append(hint)
    df["apply_url_check_needed"] = wrap_flags
    df["wrapper_employer_hint"] = wrap_hints

    # ── Phase 4 enrichment (2026-05-16 merge) ──
    # Per-row domain inference + gate flags, sourced from
    # refresh_lib.domain_inference so both pipelines stay aligned. These
    # columns are advisory: they DO NOT change triage_verdict (which is
    # already finalised above). Wei reads them as additional context when
    # spot-checking the apply pool. Surfaces three failure modes that the
    # legacy pipeline misses today:
    #   1. CSV `domain` column empty/`?` → infer from title+desc+company
    #   2. JD looks senior-titled but body says junior/intern/freelance
    #   3. Tier estimate from inferred domain disagrees with comp band
    if _DOMAIN_INFERENCE_AVAILABLE:
        inferred_domains: list[str] = []
        estimated_tiers: list[str] = []
        gate_flags: list[str] = []
        for _, row in df.iterrows():
            title_s = str(row.get("title") or "")
            desc_s = str(row.get("description") or "")
            company_s2 = str(row.get("company") or "")
            loc_s = str(row.get("location") or "")
            csv_domain = str(row.get("domain") or "").strip()

            # Domain: trust CSV column if non-empty/non-?, else infer.
            if csv_domain and csv_domain not in {"?", "unknown"}:
                inferred = csv_domain
            else:
                inferred_opt = _di_infer_domain(title_s, desc_s, company_s2)
                inferred = inferred_opt or ""

            # Tier estimate from the domain.
            tier_opt = _di_estimate_tier(inferred) if inferred else None
            tier_str = f"T{tier_opt}" if tier_opt is not None else ""

            # Gate flags (level / contract / stack / non-US).
            try:
                stack_n = int(row.get("stack_hits") or 0)
            except (ValueError, TypeError):
                stack_n = 0
            gates = _di_detect_gates(
                title=title_s,
                description=desc_s,
                location=loc_s,
                stack_hits=stack_n,
            )
            flag_parts: list[str] = []
            if gates.get("level_mismatch"):
                flag_parts.append("LEVEL")
            if gates.get("contract_role"):
                flag_parts.append("CONTRACT")
            if gates.get("zero_stack_hits"):
                flag_parts.append("ZERO-STACK")
            if gates.get("manufacturing_stack"):
                flag_parts.append("MFG-STACK")
            if gates.get("non_us_location"):
                flag_parts.append("NON-US")
            flag_str = "|".join(flag_parts)

            inferred_domains.append(inferred)
            estimated_tiers.append(tier_str)
            gate_flags.append(flag_str)
        df["inferred_domain"] = inferred_domains
        df["estimated_tier"] = estimated_tiers
        df["phase4_gate_flags"] = gate_flags
    else:
        df["inferred_domain"] = ""
        df["estimated_tier"] = ""
        df["phase4_gate_flags"] = ""

    n_skip = sum(1 for v in fv if v == "skip")
    n_review = sum(1 for v in fv if v == "review")
    n_apply = sum(1 for v in fv if v == "apply")

    print(f"Source: {path}")
    print(
        f"Rows: {len(df)}  skip={n_skip}  review={n_review}  apply={n_apply}"
        + ("  [post-gates ON]" if post_gates else "  [post-gates OFF]")
    )

    if args.out:
        out_path = os.path.expanduser(args.out)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"Wrote: {out_path}")

    apply_df = df[df["triage_verdict"] == "apply"].copy()
    if apply_df.empty:
        print("\nNo rows with final verdict=apply.")
        return

    cols = [
        "track",
        "title",
        "company",
        "location",
        "min_amount",
        "max_amount",
        "jd_comp_min",
        "jd_comp_max",
        "gate2_at_145k",
        "jd_comp_snippet",
        "priority",
        "ils_estimate",
        "estimated_tier",
        "phase4_gate_flags",
        "job_url",
        "triage_rule",
    ]
    use = [c for c in cols if c in apply_df.columns]
    print("\n--- APPLY (good pipeline fit) ---\n")
    # Tab-separated for easy paste; no markdown table requirement in script stdout
    print("\t".join(use))
    for _, row in apply_df.iterrows():
        print("\t".join(str(row.get(c, "")) for c in use))


if __name__ == "__main__":
    main()

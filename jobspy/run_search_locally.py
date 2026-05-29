#!/usr/bin/env python3
"""
Job search scraper — run locally (not in sandbox).

Setup:
  python3 -m pip install python-jobspy pandas requests --break-system-packages

Usage:
  python3 run_search_locally.py

Output (under this repo's ``jobspy/results/``):
  jobspy_results_YYYYMMDD.csv
  jobspy_results_YYYYMMDD_new.csv
    (rows whose job_url was not present in any prior jobspy_results_YYYYMMDD.csv)
  search_errors.log  (failures)
  yield_log.csv (legacy 6-column rollup)
  yield_funnel.csv
    (per-run funnel incl. PE/comp, desc, US location col, JD geo/work-mode)

Tracks:
  A  — SDET / QA / Quality / Eval:  Senior–Principal, infra/tooling scope (Indeed + LinkedIn)
  B  — AI IC roles: LLM eval, dev productivity, AI tooling. Senior IC only (Indeed + LinkedIn)
  C  — PM / TPM (technical + AI-focused only): Technical PM at AI/platform startups,
       TPM at AI startups. Consumer/growth/associate PM excluded by TITLE_BLOCKERS.
       (Indeed + LinkedIn)
  G  — Google Jobs: aggregates Greenhouse/Lever/Ashby ATS boards missed by Indeed/LI
  R  — Remotive public API: remote-only board, JSON endpoint, no auth
  GH — Greenhouse: direct company board GET, parse for signal titles
  L  — Lever public API: api.lever.co/v0/postings/{company}?mode=json, no auth
  AS — Ashby public API: api.ashbyhq.com/posting-api/job-board/{company}, no auth

Excludes:
  Java/C#/C++/Ruby/mobile stack | PE-backed | clearance | intl pay
  Masters/PhD req | research scientist | data engineer | forward deployed
  comp <$130k ceiling | >3yr ML/BE exp required | Bangalore/India/offshore
  Non-USD comp in JD only when no USD anchor ($, USD, salary…$) in same 5k snippet.

Home-geo gate (after intl `is_us_remote`; driven by ``config/profile.yaml``):
  • Parses JD for US-remote vs hybrid/onsite language (not just the location column).
  • Hybrid / onsite-in-JD → keep only if JD or `location` hits ``home_metro.place_names``.
  • JD silent on remote but `location` is a **silent_office_hubs** city without "Remote" → drop.
  • # FIX-2026-05-17-LUMA: empty `location` column AND JD silent on remote → drop
    (Luma SF/UK case 2026-05-17; empirical FN rate 0.8% of daily volume).

Post-filter:
  TITLE_REQUIRED whitelist — drops any result with no test/eval/quality signal in title.
  This is the primary noise reducer (eliminated 52/54 in May 2026 batch).

Pre-screen columns (prescreen.py on every deduped row; L1 filters annotate, do not drop):
  stack_hits  int     Wei stack keyword count in description (0 for GH-track, no desc).
  yrs_req     int|?   Max year requirement from experience-anchored regex; blank = not stated.
  domain      str     native | adj | far | ? (title-first classification)
  funding     str     Series A/B/C/D, bootstrapped, $NM raised, ? = not detected
  priority    str     HIGH | MOD | LOW | ?  Triage signal: which rows need full ILS session.
                      NOT the ILS model. ? = no description; review URL manually.
                      Sort order: priority (HIGH first) -> track -> date desc.
"""

# ── Imports ────────────────────────────────────────────────────────────────────
import sys
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APPLICATIONS_DIR = os.path.join(_REPO_ROOT, 'applications')
sys.path.insert(0, os.path.join(_REPO_ROOT, 'jobspy'))
sys.path.insert(0, _APPLICATIONS_DIR)

from profile_loader import (  # noqa: E402
    comp_settings,
    enabled_tracks,
    get_profile,
    home_metro_regex,
    remote_preference,
    silent_office_hubs_regex,
)

get_profile()  # load user profile at startup (config/profile.yaml or example)

from prescreen import add_prescreen_columns  # noqa: E402
from skip_resolver import (  # noqa: E402
    SkipResolver,
    build_normalized_skip_keys,
    company_matches_skip_key,
    get_resolver,
    install_resolver,
    invalidate_default_cache,
    normalize_company_key,
    rebootstrap_from_profile,
    skip_key_variants,
)
import re
import time
import json
import html as _html
import logging
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import StringIO
from urllib.parse import urlparse, urlunparse

import pandas as pd

try:
    import requests
except ImportError:
    print("Run: python3 -m pip install requests --break-system-packages")
    sys.exit(1)

try:
    from jobspy import scrape_jobs
except ImportError:
    print("Run: python3 -m pip install python-jobspy --break-system-packages")
    sys.exit(1)

# ── Output paths ───────────────────────────────────────────────────────────────
OUT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
DATESTAMP = datetime.now().strftime('%Y%m%d')
OUT_CSV   = os.path.join(OUT_DIR, f'jobspy_results_{DATESTAMP}.csv')
OUT_NEW   = os.path.join(OUT_DIR, f'jobspy_results_{DATESTAMP}_new.csv')
ERR_LOG   = os.path.join(OUT_DIR, 'search_errors.log')

os.makedirs(OUT_DIR, exist_ok=True)
logging.basicConfig(
    filename=ERR_LOG,
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(message)s',
)

_FULL_CSV_NAME = re.compile(r'^jobspy_results_(\d{8})\.csv$')


def normalize_job_url(url: object) -> str:
    """Stable key for cross-run dedup: scheme + netloc + path; no query, fragment, or trailing slash."""
    if url is None or (isinstance(url, float) and pd.isna(url)):
        return ''
    s = str(url).strip()
    if not s or s.lower() == 'nan':
        return ''
    try:
        p = urlparse(s)
    except Exception:
        return ''
    scheme = (p.scheme or 'https').lower()
    netloc = (p.netloc or '').lower()
    path = (p.path or '').rstrip('/')
    return urlunparse((scheme, netloc, path, '', '', ''))


def load_seen_job_urls(out_dir: str, exclude_basename: str) -> set[str]:
    """Union of normalized job_url from prior full daily exports (excludes today's file if re-run)."""
    seen: set[str] = set()
    if not os.path.isdir(out_dir):
        return seen
    for name in sorted(os.listdir(out_dir)):
        if name == exclude_basename or not _FULL_CSV_NAME.match(name):
            continue
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            ju = pd.read_csv(path, usecols=['job_url'], dtype=str)
        except (ValueError, pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
            continue
        for u in ju['job_url']:
            k = normalize_job_url(u)
            if k:
                seen.add(k)
    return seen


# ── Track A: QA / SDET / Quality / Eval ──────────────────────────────────────
# NOTE: Keep queries SHORT (2-4 words). "python" belongs in descriptions, not titles.
# LinkedIn/Indeed multi-keyword title searches are near-literal — long queries kill recall.
TRACK_A = [
    'senior SDET remote',
    'staff SDET remote',
    'principal SDET remote',
    'senior software engineer in test remote',
    'staff software engineer in test',
    'AI quality engineer remote',
    'AI evaluation engineer remote',
    'LLM evaluation engineer',
    'quality platform engineer remote',
    'test infrastructure engineer remote',
    'senior QA automation engineer remote',
    'principal QA engineer remote',
    'senior SDET AI remote',
    'software engineer in test AI quality',
    'AI observability quality engineer',
    'senior quality engineer automation remote',
    'quality engineering lead remote',
]

# ── Track B: AI IC roles — LLM eval, dev productivity, AI tooling ────────────
TRACK_B = [
    'AI evaluation engineer senior remote',
    'LLM evaluation engineer senior',
    'developer productivity engineer AI remote',
    'AI tooling engineer senior remote',
    'generative AI quality engineer',
    'LLM evaluation testing senior remote',
    'AI red team evaluation engineer',
    'model quality engineer remote',
    'AI quality assurance engineer senior',
    'LLM output quality engineer remote',
]

# ── Track C: PM / TPM — Technical + AI-focused only ─────────────────────────
# Target: Technical PM (internal tooling / AI platform) and TPM at AI startups.
# Consumer PM, growth PM, associate PM = excluded by TITLE_BLOCKERS.
TRACK_C = [
    'technical program manager AI remote',
    'technical program manager platform remote',
    'AI product manager platform remote',
    'technical product manager AI tooling',
    'TPM AI startup remote',
    'technical program manager engineering remote',
    'AI product manager developer tools remote',
    'program manager AI platform remote senior',
]

# ── Track G: Google Jobs ──────────────────────────────────────────────────────
# Google Jobs aggregates ATS boards (Greenhouse, Lever, Ashby, Workday) that
# Indeed/LinkedIn index less reliably. Use natural-language phrases.
GOOGLE_QUERIES = [
    'senior SDET AI remote jobs',
    'software engineer in test LLM evaluation remote',
    'AI evaluation engineer senior remote jobs',
    'LLM evaluation engineer senior remote',
    'quality platform engineer AI remote',
    'developer productivity engineer AI remote senior',
    'AI observability engineer quality remote',
    'technical program manager AI startup remote jobs',
    'AI product manager platform tooling remote jobs',
    'technical product manager AI developer tools',
]

# ── ATS company slugs (file-driven; fork without editing Python) ───────────────
# Primary: jobspy/results/companies_{ashby,gh,lever}.txt (gitignored overrides)
# Bundled examples: config/ats_companies_*.example.txt
# Per-run additions: jobspy/results/extra_{ashby,gh,lever}.txt


def _load_slug_file(filepath: str, *, label: str | None = None) -> list[str]:
    try:
        with open(filepath, encoding='utf-8') as f:
            slugs = [
                ln.split('#', 1)[0].strip()
                for ln in f
                if ln.split('#', 1)[0].strip()
            ]
        if slugs and label:
            print(f'[{label}] Loaded {len(slugs)} slugs from {os.path.basename(filepath)}')
        return slugs
    except OSError:
        return []


def _load_ats_companies(ats_name: str) -> list[str]:
    """Results override first, then bundled config example."""
    candidates = [
        os.path.join(OUT_DIR, f'companies_{ats_name}.txt'),
        os.path.join(_REPO_ROOT, 'config', f'ats_companies_{ats_name}.example.txt'),
    ]
    for path in candidates:
        slugs = _load_slug_file(path, label=ats_name)
        if slugs:
            return slugs
    return []


LEVER_COMPANIES = _load_ats_companies('lever')
ASHBY_COMPANIES = _load_ats_companies('ashby')
GREENHOUSE_COMPANIES = _load_ats_companies('gh')

# ── Skip lists (shared skip_resolver) ─────────────────────────────────────────
_profile_paths = get_profile().get('paths') or {}
_SKIP_COMPANIES_TXT = _profile_paths.get('skip_companies') or os.path.join(
    _APPLICATIONS_DIR, 'skip_companies.txt',
)
_INDEX_HTML = _profile_paths.get('application_index') or os.path.join(
    _APPLICATIONS_DIR, 'application_index.html',
)
_SKIP_RESOLVER = SkipResolver.bootstrap(
    _APPLICATIONS_DIR, _SKIP_COMPANIES_TXT, _INDEX_HTML,
)
install_resolver(_SKIP_RESOLVER)
SKIP_COMPANIES = _SKIP_RESOLVER.raw_skip_companies


def refresh_skip_resolver() -> SkipResolver:
    """Re-bootstrap skip list from the current profile (e.g. after QA_JOB_PROFILE change)."""
    global _SKIP_RESOLVER, SKIP_COMPANIES
    _SKIP_RESOLVER = rebootstrap_from_profile(_APPLICATIONS_DIR)
    SKIP_COMPANIES = _SKIP_RESOLVER.raw_skip_companies
    return _SKIP_RESOLVER


# Extra slugs per run (optional; merged after base ATS lists):
#   jobspy/results/extra_ashby.txt, extra_gh.txt, extra_lever.txt
_EXTRA_FILES = {
    'ashby': os.path.join(OUT_DIR, 'extra_ashby.txt'),
    'gh': os.path.join(OUT_DIR, 'extra_gh.txt'),
    'lever': os.path.join(OUT_DIR, 'extra_lever.txt'),
}

ASHBY_COMPANIES += _load_slug_file(_EXTRA_FILES['ashby'], label='extra-ashby')
GREENHOUSE_COMPANIES += _load_slug_file(_EXTRA_FILES['gh'], label='extra-gh')
LEVER_COMPANIES += _load_slug_file(_EXTRA_FILES['lever'], label='extra-lever')

TITLE_BLOCKERS = {
    'java developer','c# developer','ruby developer','mobile engineer',
    'ios engineer','android engineer','data engineer','data scientist',
    'research scientist','research engineer','ml engineer',
    'machine learning engineer','forward deployed','director','vp ',
    'vice president','manager','scrum master','site reliability',
    'devops','security engineer','network engineer','systems engineer',
    'sales engineer','solutions engineer','support engineer',
    'technical writer','recruiter','instructor','teacher',
    'backend engineer','backend developer','frontend engineer',
    'full stack engineer','fullstack engineer','full-stack engineer',
    'build engineer','bioinformatics','analog engineer','analog design',
    'product analyst','data architect','data scraping',
    'cloud architect','cloud security','legal engineer',
    'professional services','technical architect',
    'head of engineering','staff engineering lead','engineering lead',
    'principal data','software engineer intern','intern',
    'project leader','advisory services',
    # SWE titles that slip through via dev-productivity signal — wrong career track
    'staff+ software engineer','staff software engineer, developer',
    # Non-QA analyst titles (healthcare BI, data analyst, etc.)
    'business intelligence analyst','data analyst','bi analyst',
    # Wrong-shape PM roles (consumer, growth, associate, marketing)
    'associate product manager','associate pm',
    'growth product manager','growth pm',
    'consumer product manager',
    'marketing product manager','product marketing',
    'product operations','chief of staff',  # not PM/TPM equivalents
    # Hardware / manufacturing QA (not software)
    'supplier quality','manufacturing quality','rma quality',
    'incoming quality','production quality','incoming inspection',
    'field quality','process quality','supplier engineer',
    'manufacturing engineer','industrial engineer','hardware engineer',
    'eastern european based',  # Overjet-class geo-locked titles
    'electrical engineer','mechanical engineer','firmware engineer',
    'embedded engineer','rf engineer','systems test engineer',
    'validation engineer',        # often hardware/EE context; too broad alone but catches Mitsubishi-style
    # Construction / physical infrastructure
    'construction qa','infrastructure qa','civil engineer',
    # Manual-only (no automation) — flag but don't hard-block (use desc filter if needed)
    # 'manual qa',   # NOT blocking — manual+automation combos are fine
}

# Title REQUIRED signal — whitelist. Result dropped if none of these appear.
TITLE_REQUIRED = [
    'sdet',
    'software engineer in test',
    ' set ',            # space-padded: avoids "asset", "reset"
    'quality engineer',
    'quality assurance', # catches "Quality Assurance Engineer", "Quality Assurance Lead"
    'qa engineer',
    'qa ',              # catches "QA Automation Lead", "QA Lead", "QA Engineer" (start/mid)
    ' qa',              # catches "Senior QA", "Staff QA", "Principal QA" (end/mid)
    'qe ',              # catches "QE Lead", "QE Engineer" (mid/start)
    ' qe',              # catches "Senior QE", "Staff QE" (end/mid)
    'test engineer',
    'test automation',
    'evaluation engineer',
    'eval engineer',
    'llm eval',
    'llm evaluation',
    'model eval',
    'model quality',
    'ai quality',
    'ai eval',
    'quality platform',
    'quality lead',
    'qa lead',
    'developer productivity',
    'dev productivity',
    'test infrastructure',
    'automation engineer',
    # PM / TPM signals (technical + AI-focused only; consumer/growth filtered by TITLE_BLOCKERS)
    'technical program manager',
    'engineering program manager',  # distinct from TPM; valid at mid-size tech
    ' tpm ',            # space-padded mid-string
    'tpm ',             # start of title
    ' tpm',             # end of title
    'ai product manager',
    'technical product manager',
    # 'product owner' REMOVED 2026-05-15 per Wei feedback: PO is a senior PM
    # function at most companies (5-10+ yrs, PM-track comp), not QA-adjacent.
    # CSPO cert is relevant but the title-whitelist match was sucking yield
    # budget. PO roles must be re-introduced via a dedicated PM/PO track if Wei
    # decides to pursue them separately.
]

# ── Compiled regex patterns (compiled once, not per-row) ─────────────────────
# Plain strings use substring match; raw strings use re.search.
_DESC_PLAIN = [
    'travel required','up to 25% travel','up to 50% travel',
    'security clearance required','top secret','clearance required',
    "master's degree required","master's required","ms required",
    'phd required','ph.d required',
    'java required','requires java','primary language: java',
    'c# required','c++ required',
    'statistics degree',
    'forward deployed','on-site only','onsite:','relocation required',
    'international compensation','non-us',
    # # FIX-2026-05-17-LUMA: UX-research roles surfacing under 'evaluation engineer'
    # title-whitelist (caught Luma 2026-05-17). Bare substring; widen later if FPs surface.
    'ux research','ux researcher','qualitative researcher',
    'user experience research','design research',
    'tensorflow required','pytorch required',
    'kubeflow','mlflow required',
    # Geo-restricted non-US roles (catches listings where jobspy returns NaN location
    # but the description explicitly limits to a non-US geography)
    'must be located in the philippines','based in the philippines',
    'must be located in india','based in india',
    'must be located in canada','based in canada',
    'eu citizens only','must be based in europe','eu only',
    'must reside in',    'must be located in latin america',
    'currently based in mexico','based in mexico','work from anywhere in mexico',
    'national quality systems',  # NQS — written-off; catches Indeed rows with empty company
    'based in eastern europe','located in eastern europe','eastern european candidates',
    'must be based in eastern europe',
    # India-only / offshore DC phrasing (NEOGOV-class)
    'india development center', 'development center in india',
    'remote opportunities for our india', 'opportunities for our india',
    'position is based in india', 'based in india only', 'candidates in india only',
    'employees in india', 'hiring in india only', 'idc in india',
    # EU / UK right-to-work-only (Entrust-class)
    'right to work in the eu', 'right to work in the uk', 'right to work in europe',
    'must be eligible to work in the european union', 'eligible to work in the uk',
    'eu work authorization', 'uk work authorization', 'must be legally authorized to work in the uk',
    'must have the right to work in the uk', 'must have the right to work in the eu',
    # Fed clearance (Strategic Technology Partners / Sierra 7–class); keep tight strings
    'ts/sci', 't/s/sci', 'sci eligibility', 'dod clearance', 'public trust',
    'u.s. government security clearance', 'federal background investigation',
]
_DESC_REGEX = [
    re.compile(r'3\+ years.*machine learning'),
    re.compile(r'5\+ years.*machine learning'),
    re.compile(r'3\+ years.*deep learning'),
    re.compile(r'3\+ years.*model training'),
    re.compile(r'5\+ years.*model training'),
    # # FIX-2026-05-17-LUMA: Master's/PhD in non-CS field (caught Luma's HCI/Psych phrasing).
    re.compile(
        r"(?:master'?s?|phd|doctorate)\s+(?:degree\s+)?"
        r"(?:or\s+higher\s+)?in\s+"
        r"(?:cognitive\s+science|human[-\s]?computer\s+interaction|hci\b|"
        r"design\s+research|psychology|media\s+studies|cognitive\s+psychology|"
        r"experimental\s+psychology|neuroscience|linguistics|sociology|"
        r"anthropology|philosophy)",
        re.IGNORECASE,
    ),
    # Medical-device / healthcare compliance certs — immediate screen-out for QA
    # candidates without regulated-industry experience (ISO 14971, 21 CFR 820,
    # IEC 62304, ISO 13485, MDSAP, MDR/MDD).
    re.compile(
        r'\b(?:iso\s+14971|21\s+cfr\s+part\s+820|iec\s+62304|iso\s+13485|mdsap|mdr)\b',
        re.IGNORECASE,
    ),
]

# Non-USD comp in JD: only hard-drop when the snippet shows foreign pay *without*
# any USD pay anchor (see feedback_jd_nonUS_detection.md — avoid blanket symbol bans).
_JD_NON_USD_COMP = re.compile(
    r'(?:'
    r'[£€₹]|'
    r'\b(?:mxn|mx\$|gbp|eur|inr)\b(?:\s|$|[,/])|'
    r'(?:salary|compensation|package|pay|offer)\s*[:#]?\s*.{0,90}?(?:[£€₹]|\b(?:mxn|gbp|eur|inr)\b)|'
    r'(?:/|\s)(?:year|yr|month|mo)\s*[/ ]\s*(?:gbp|eur|mxn|inr)|'
    r'(?:per|/)\s*(?:hour|hr)\s*.{0,20}?(?:[£€₹]|\b(?:gbp|eur|mxn|inr)\b)|'
    r'(?:[£€₹]\s*\d|\d\s*(?:/|per)\s*(?:hour|hr)\s*(?:[£€₹]|\b(?:gbp|eur)\b))'
    r')',
    re.IGNORECASE,
)
_JD_USD_COMP_ANCHOR = re.compile(
    r'(?:'
    r'\$\s*\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b'
    r'|\$\s*\d{2,6}(?:\.\d{2})?\b'
    r'|\$\s*\d{2,4}k\b'
    r'|\bUSD\b'
    r'|\bUS\s*\$\b'
    r'|\b(?:salary|compensation|base pay|package|pay range)\b.{0,120}?\$'
    r')',
    re.IGNORECASE,
)
_PE_SIGNALS = [
    'thoma bravo','vista equity','leonard green','ta associates',
    'francisco partners','kkr portfolio','warburg pincus','apax',
    'permira','bain capital','silver lake','carlyle',
    'waud capital', 'waud',
]
# Hard international blockers — fire even if "Remote" also appears in the string.
# e.g. "Remote - Canada" or "Remote (EMEA)" should still be blocked.
# NOTE: 'georgia' intentionally omitted — US state; use 'tbilisi' for Georgia (country).
# NOTE: 'st. petersburg' omitted — use 'russia' + 'moscow' etc. to catch Russian cities.
# NOTE: 'cali' omitted — abbreviation collision with California; use 'colombia'+'bogota'.
_INTL_HARD = re.compile(
    # South Asia
    r'\bindia\b|\bbangalore\b|\bbengaluru\b|\bhyderabad\b|\bpune\b|\bmumbai\b'
    r'|\bdelhi\b|\bnew delhi\b|\bchennai\b|\bkolkata\b|\bnoida\b|\bgurgaon\b|\bgurugram\b'
    r'|\bpakistan\b|\bkarachi\b|\blahore\b|\bislamabad\b'
    r'|\bbangladesh\b|\bdhaka\b|\bsri lanka\b|\bcolombo\b|\bnepal\b|\bkathmandu\b'
    # Southeast Asia
    r'|\bphilippines\b|\bmanila\b|\bcebu\b'
    r'|\bvietnam\b|\bho chi minh\b|\bhanoi\b'
    r'|\bindonesia\b|\bjakarta\b|\bbali\b'
    r'|\bmalaysia\b|\bkuala lumpur\b|\bthailand\b|\bbangkok\b|\bmyanmar\b'
    # East + Southeast (city-states / hubs)
    r'|\bsingapore\b'
    # East Asia
    r'|\bchina\b|\bbeijing\b|\bshanghai\b|\bshenzhen\b|\bguangzhou\b|\bhong kong\b'
    r'|\bjapan\b|\btokyo\b|\bosaka\b'
    r'|\bsouth korea\b|\bseoul\b|\bbusan\b|\btaiwan\b|\btaipei\b'
    # Oceania
    r'|\baustralia\b|\bsydney\b|\bmelbourne\b|\bbrisbane\b|\bperth\b|\badelaide\b|\bcanberra\b'
    r'|\bnew zealand\b|\bauckland\b|\bwellington\b|\bchristchurch\b'
    # Canada
    r'|\bcanada\b|\btoronto\b|\bvancouver\b|\bmontreal\b|\bcalgary\b|\bottawa\b'
    r'|\bedmonton\b|\bquebec\b|\bhalifax\b|\bwinnipeg\b|\bkitchener\b|\bwaterloo\b'
    # UK / Ireland
    r'|\bunited kingdom\b|\bu\.k\b|\blondon\b|\bmanchester\b|\bedinburgh\b'
    r'|\bglasgow\b|\bbristol\b|\bleeds\b|\bcork\b|\bireland\b|\bdublin\b'
    # Western Europe
    r'|\bgermany\b|\bberlin\b|\bmunich\b|\bfrankfurt\b|\bhamburg\b|\bcologne\b|\bstuttgart\b'
    r'|\bfrance\b|\bparis\b|\blyon\b|\bmarseille\b'
    r'|\bspain\b|\bmadrid\b|\bbarcelona\b|\bvalencia\b|\bbilbao\b'
    r'|\bportugal\b|\blisbon\b|\bporto\b'
    r'|\bnetherlands\b|\bamsterdam\b|\brotterdam\b|\butrecht\b'
    r'|\bbelgium\b|\bbrussels\b|\bantwerp\b'
    r'|\bswitzerland\b|\bzurich\b|\bgeneva\b|\bbasel\b|\bbern\b'
    r'|\baustria\b|\bvienna\b|\bgraz\b'
    r'|\bsweden\b|\bstockholm\b|\bgothenburg\b|\bmalmo\b'
    r'|\bnorway\b|\boslo\b|\bbergen\b'
    r'|\bdenmark\b|\bcopenhagen\b'
    r'|\bfinland\b|\bhelsinki\b'
    r'|\bluxembourg\b|\bmalta\b|\bcyprus\b|\bnicosia\b|\biceland\b|\breykjavik\b'
    # Central / Eastern Europe
    r'|\bpoland\b|\bwarsaw\b|\bkrakow\b|\bwroclaw\b|\bgdansk\b|\bpoznan\b'
    r'|\bczech republic\b|\bczechia\b|\bprague\b|\bbrno\b|\bostrava\b'
    r'|\bslovakia\b|\bbratislava\b|\bhungary\b|\bbudapest\b'
    r'|\bromania\b|\bbucharest\b|\bcluj\b|\biasi\b|\btimisoara\b'
    r'|\bbulgaria\b|\bsofia\b|\bvarna\b'
    r'|\bserbia\b|\bbelgrade\b|\bnovi sad\b'
    r'|\bcroatia\b|\bzagreb\b|\bsplit\b'    # 'split' is also English but fine in location context
    r'|\bslovenia\b|\bljubljana\b'
    r'|\bgreece\b|\bathens\b|\bthessaloniki\b'
    r'|\bturkey\b|\bistanbul\b|\bankara\b|\bizmir\b'
    r'|\brussia\b|\bmoscow\b|\bnovosibirsk\b|\byekaterinburg\b|\bkazan\b'
    r'|\bukraine\b|\bkyiv\b|\bkharkiv\b|\blviv\b|\bodessa\b|\bdnipro\b'
    r'|\bbelarus\b|\bminsk\b|\blithuania\b|\bvilnius\b|\bkaunas\b'
    r'|\blatvia\b|\briga\b|\bestonia\b|\btallinn\b|\bmoldova\b|\bchisinau\b'
    r'|\balbania\b|\btirana\b|\bnorth macedonia\b|\bskopje\b'
    r'|\bbosnia\b|\bsarajevo\b|\bmontenegro\b|\bpodgorica\b|\bkosovo\b'
    # Middle East
    r'|\bisrael\b|\btel aviv\b|\bjerusalem\b|\bhaifa\b'
    r'|\buae\b|\bdubai\b|\babu dhabi\b|\bsharjah\b'
    r'|\bsaudi arabia\b|\briyadh\b|\bjeddah\b'
    r'|\bqatar\b|\bdoha\b|\bkuwait\b|\bbahrain\b|\bmanama\b|\boman\b|\bmuscat\b'
    r'|\bjordan\b|\bamman\b|\blebanon\b|\bbeirut\b|\biraq\b|\bbaghdad\b'
    r'|\biran\b|\btehran\b'
    # Africa
    r'|\bsouth africa\b|\bcape town\b|\bjohannesburg\b|\bdurban\b|\bpretoria\b'
    r'|\bkenya\b|\bnairobi\b|\bnigeria\b|\blagos\b|\babuja\b'
    r'|\bghana\b|\baccra\b|\begypt\b|\bcairo\b|\balexandria\b'
    r'|\bmorocco\b|\bcasablanca\b|\brabat\b|\bethiopia\b|\baddis ababa\b'
    r'|\btanzania\b|\bdar es salaam\b|\buganda\b|\bkampala\b|\bsenegal\b|\bdakar\b'
    r'|\balgeria\b|\balgiers\b|\btunisia\b|\btunis\b|\bsudan\b|\bkhartoum\b'
    # Latin America
    r'|\bmexico\b|\bguadalajara\b|\bmonterrey\b'    # not 'mexico city' — 'city' alone is fine
    r'|\bbrazil\b|\bsao paulo\b|\brio de janeiro\b|\bcuritiba\b|\bfortaleza\b'
    r'|\bargentina\b|\bbenos aires\b|\bbemos aires\b|\brosario\b'
    r'|\bchile\b|\bsantiago\b'
    r'|\bcolombia\b|\bbogota\b|\bmedell\w+\b'          # medellín + typo variants
    r'|\bperu\b|\blima\b|\becuador\b|\bquito\b|\bguayaquil\b'
    r'|\bvenezuela\b|\bcaracas\b|\bbolivia\b|\bla paz\b'
    r'|\buruguay\b|\bmontevideo\b|\bparaguay\b|\basuncion\b'
    r'|\blatam\b|\blatin america\b'
    r'|\bcosta rica\b|\bpanama\b|\bguatemala\b|\bhonduras\b|\bnicaragua\b'
    r'|\btegucigalpa\b|\bfrancisco moraz[aá]n\b|\bsan pedro sula\b'
    # Central Asia + South Caucasus
    r'|\bkazakhstan\b|\balmaty\b|\bnur-sultan\b|\bastana\b'
    r'|\buzbekistan\b|\btashkent\b|\bkyrgyzstan\b|\btajikistan\b|\bturkmenistan\b'
    r'|\btbilisi\b|\barmenia\b|\byerevan\b|\bazerbaijan\b|\bbaku\b'
    # Broad blockers
    r'|\bemea\b|\bapac\b|\bglobal \(non-us\)\b|\boutside (?:the )?us\b',
    re.IGNORECASE,
)

# Positive US / remote signals. Checked AFTER _INTL_HARD fails.
_US_GEO = re.compile(
    r'(?:'
    # Remote / nationwide
    r'remote|united states|\busa\b|\bu\.s\.a\b|\bu\.s\b|\bconus\b'
    r'|north america|anywhere|worldwide|work from home|\bwfh\b|us only|domestic'
    r'|us-based|u\.s\.-based'
    r'|'
    # All 50 US state full names
    r'alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware'
    r'|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana'
    r'|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana'
    r'|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina'
    r'|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina'
    r'|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia'
    r'|wisconsin|wyoming|district of columbia|washington d\.?c'
    r'|'
    # 2-letter US state abbreviations.
    # NOTE: the outer `re.IGNORECASE` flag below makes these match case-insensitively
    # despite being written uppercase. Earlier comment claimed case-sensitivity; that
    # was wrong. Behavior: `\bGA\b` matches 'GA', 'ga', 'Ga', etc. The state-name
    # alternation above (now including 'georgia') makes this redundant for Georgia
    # specifically, but kept for the other 49 + DC.
    r'\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN'
    r'|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA'
    r'|WV|WI|WY|DC)\b'
    r'|'
    # Major US cities
    r'atlanta|chicago|boston|seattle|denver|austin|san francisco|los angeles'
    r'|new york|dallas|houston|phoenix|philadelphia|san antonio|san diego|san jose'
    r'|jacksonville|fort worth|columbus|charlotte|indianapolis|salt lake city'
    r'|nashville|portland|las vegas|memphis|raleigh|louisville|richmond|baltimore'
    r'|milwaukee|albuquerque|tucson|fresno|sacramento|mesa|kansas city|omaha'
    r'|minneapolis|tampa|new orleans|arlington|wichita|pittsburgh|anchorage'
    r'|cincinnati|greensboro|orlando|plano|henderson|lincoln|chandler'
    r'|norfolk|madison|durham|lubbock|garland|glendale|hialeah|reno'
    r'|baton rouge|irvine|chesapeake|irving|scottsdale|fremont|gilbert|spokane'
    r'|des moines|fayetteville|tacoma|huntsville|little rock|grand rapids'
    r'|el paso|st\. louis|rochester|birmingham|providence|yonkers|huntington beach'
    r')',
    re.IGNORECASE,
)

# ── HTML stripping ─────────────────────────────────────────────────────────────
class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
    def handle_data(self, d):
        self._parts.append(d)
    def get_text(self):
        return ' '.join(self._parts)

def strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html or '')
    return s.get_text()

# ── Greenhouse job board HTML parser ──────────────────────────────────────────
class _GHJobParser(HTMLParser):
    """
    Extracts (title, location, href) triples from a Greenhouse board page.

    Greenhouse boards embed location in a <span> inside the job <a> tag:
      <a href="/co/jobs/123">Job Title<span class="...">City, Country</span></a>

    We track span depth so title text (direct child) and location text (span child)
    are captured separately, preventing "QA EngineerBengaluru, India" concatenation.
    """
    def __init__(self):
        super().__init__()
        self.jobs = []
        self._in_link = False
        self._span_depth = 0
        self._href = ''
        self._title = ''
        self._location = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._in_link = True
            self._href = dict(attrs).get('href', '')
            self._title = ''
            self._location = ''
            self._span_depth = 0
        elif tag == 'span' and self._in_link:
            self._span_depth += 1

    def handle_endtag(self, tag):
        if tag == 'a' and self._in_link:
            if self._href and 'jobs' in self._href:
                self.jobs.append((
                    self._title.strip(),
                    self._location.strip(),
                    self._href,
                ))
            self._in_link = False
            self._span_depth = 0
        elif tag == 'span' and self._in_link:
            self._span_depth = max(0, self._span_depth - 1)

    def handle_data(self, data):
        if not self._in_link:
            return
        if self._span_depth == 0:
            self._title += data      # direct text node = job title
        else:
            self._location += data   # inside span = location or metadata

# Post-processing: some Greenhouse boards (e.g. Dialpad) embed location directly
# in the title text node rather than a child <span>, producing:
#   "QA Automation EngineerBengaluru, India"   (lowercase → UPPER transition)
#   "Sr. SDETKitchener, Canada"                (ALL-CAPS acronym → TitleCase city)
#   "Senior QA Automation EngineerBengaluru, Karnataka, India"  (multi-part loc)
#
# Two-pass split:
#   Pass 1 (lowercase→UPPER): fires when a lowercase letter immediately precedes
#     the city start — "Engineer[r]→[B]engaluru". Lookbehind (?<=[a-z]).
#   Pass 2 (ALL-CAPS acronym→TitleCase city): fires when an all-caps acronym
#     (3-10 chars) is immediately followed by a TitleCase word (upper+lower) —
#     "SDET[K]itchener". Captures both groups; split at group(2) start.
#
# Space is intentionally NOT in the city character class — it would make the
# regex match from pos 0 when the title starts with a capital letter, causing
# the guards to fail (same bug as before). Multi-word cities use the optional
# (?:\s[A-Z][a-zA-Z]{1,20})? sub-group instead.

_GH_SPLIT_LOWER = re.compile(            # "EngineerBengaluru, India"
    r'(?<=[a-z])'                         # char before match is lowercase (no space)
    r'([A-Z][a-zA-Z]{2,25}'              # city: 3–26 chars, starts with uppercase
    r'(?:\s[A-Z][a-zA-Z]{1,20})?'        # optional 2nd city word: " York" in "New York"
    r'(?:,\s*[A-Z][a-zA-Z]{1,25})*'      # zero or more ", State/Country" parts
    r')',
    re.UNICODE,
)
_GH_SPLIT_ACRONYM = re.compile(          # "SDETKitchener, Canada"
    r'([A-Z]{3,10})'                      # all-caps acronym: SDET, SET, QAE, etc.
    r'([A-Z][a-z][a-zA-Z]{0,22}'         # city: TitleCase word (upper + lower required)
    r'(?:\s[A-Z][a-zA-Z]{1,20})?'        # optional 2nd city word
    r'(?:,\s*[A-Z][a-zA-Z]{1,25})*'      # zero or more ", State/Country" parts
    r')',
    re.UNICODE,
)

def _split_gh_title_location(title: str, location: str) -> tuple[str, str]:
    """
    Split a Greenhouse concat title into (job_title, location).
    Only fires when location is empty (parser produced no <span> location).
    """
    if location:
        return title, location
    # Pass 1: word ending in lowercase immediately before the city
    m = _GH_SPLIT_LOWER.search(title)
    if m:
        return title[:m.start()].strip(), m.group(1).strip()
    # Pass 2: all-caps acronym before TitleCase city
    m = _GH_SPLIT_ACRONYM.search(title)
    if m:
        city_start = m.start(2)
        return title[:city_start].strip(), m.group(2).strip()
    return title, location

# ── Filter functions ──────────────────────────────────────────────────────────
# Re-export skip helpers for tests and triage (implementation: skip_resolver).


def is_skip_company(name: object) -> bool:
    return get_resolver().is_skip_company(name)


def skip_company_match_key(name: object) -> str | None:
    return get_resolver().skip_company_match_key(name)


def is_skip_title_company_signal(title: str) -> bool:
    return get_resolver().is_skip_title_company_signal(title)


# Back-compat for tests that touched private helpers.
_skip_key_variants = skip_key_variants
_build_normalized_skip_keys = lambda: build_normalized_skip_keys(SKIP_COMPANIES)
_company_matches_skip_key = company_matches_skip_key

# ── Title-level regex blockers (Patch 4: 20260515 false-positive learnings) ──
# All patterns survived an adversarial review:
#   1. Country tokens overwhelmingly mean role geo when in a title; the listed
#      set is restricted to names with no common US-context homonyms.
#   2. UK cities Birmingham + London have US homonyms (Birmingham AL, London
#      KY/Ontario); negative-lookaheads carve them out.
#   3. Foreign country-code parens explicitly exclude US states (CA, AL, WA…)
#      and ambiguous abbreviations (IN, US, USA).
#   4. Parenthesized primary stack is the role's authoritative stack signal;
#      `(C#)`/`(Java)` in a title is the hiring team naming their language.
_TITLE_BLOCKER_REGEXES = [
    # Foreign country tokens (role-location signal in titles).
    re.compile(
        r"\b(?:brazil|brazilian|mexico|mexican|india|indian|poland|polish|"
        r"ukraine|ukrainian|romania|romanian|argentina|colombia|peru|"
        r"spain|spanish|portugal|portuguese|philippines|vietnam|vietnamese)\b"
    ),
    # UK / Ireland cities (with US-homonym guards for Birmingham + London).
    re.compile(
        r"\b(?:leicester|manchester|edinburgh|glasgow|bristol|dublin|cork|"
        r"birmingham(?!,?\s*(?:al|alabama|mi|michigan))|"
        r"london(?!,?\s*(?:ky|kentucky|on|ontario|tx|texas|oh|ohio)))\b"
    ),
    # Foreign country-code parenthetical suffix.
    # Explicitly excludes US states (ca, al, wa, or, tx, mi, ky, nj, ny, ma,
    # nc, co, ga, md, il, pa, oh, va, fl, az, mn, mo, in*, …) and the
    # ambiguous codes us/usa/ca/in.
    re.compile(
        r"\((?:pl|ua|br|mx|ro|cz|hu|pt|nl|de|fr|it|es|ie|gr|dk|fi|se|no|tr|"
        r"ar|cl|pe|ph|vn|th|sg|hk|tw|kr|jp|cn|ru|by)\)"
    ),
    # Parenthesized primary stack — Wei-confirmed hard blockers.
    re.compile(r"\((?:c#|c\s*sharp|java|ruby|c\+\+|objective[- ]?c)\)"),
]


def has_title_blocker(title: str) -> bool:
    t = str(title).lower()
    if any(b in t for b in TITLE_BLOCKERS):
        return True
    return any(rx.search(t) for rx in _TITLE_BLOCKER_REGEXES)

def has_required_signal(title: str) -> bool:
    t = str(title).lower()
    return any(s in t for s in TITLE_REQUIRED)

def has_desc_blocker(desc) -> bool:
    if not desc or (isinstance(desc, float)):
        return False
    # Cap at 5000 chars — avoids ReDoS on pathologically long descriptions.
    # Patch 5b: unescape LinkedIn-escaped punctuation so prose regexes match.
    d = _unescape_jd_body(str(desc)[:5000].lower())
    if any(p in d for p in _DESC_PLAIN):
        return True
    if any(rx.search(d) for rx in _DESC_REGEX):
        return True
    # Patch 6: JD-body geo / reposter signals not caught by location column or title.
    if has_body_geo_or_reposter_blocker(d):
        return True
    # Patch 2026-05-15 #2: hourly-rate comp with annualized ceiling below $110k
    # floor. Takes the FULL desc (not the 5000-char prose window) because pay-
    # transparency blocks are typically at the bottom of LinkedIn JDs.
    if has_low_hourly_comp(desc):
        return True
    # Patch 2026-05-15 #3: gaming-stack wheelhouse-miss (3+ distinct tokens).
    if has_gaming_wheelhouse_miss(d):
        return True
    # Foreign-currency / non-USD pay framing only when no USD pay anchor in same window
    if _JD_NON_USD_COMP.search(d) and not _JD_USD_COMP_ANCHOR.search(d):
        return True
    return False


# ── Body geo + reposter blockers (Patch 6: 20260515 false-positive learnings) ──
# Detect role-geo signals embedded in the JD body that aren't surfaced by the
# location column or title. Each clause is paired with a US-remote-claim
# escape so genuinely US-remote roles at companies with global hubs pass
# through. The Outlier reposter pattern fires unconditionally (reposters do
# not also claim US-remote).
_BODY_GEO_INDIA_HUB = re.compile(
    # Apostrophe class includes ASCII ' and unicode right-quote ’ — LinkedIn
    # JDs typically use the typographic ’ in possessives ("Company's").
    r"\bindia\s+is\s+(?:one\s+of\s+)?[\w\s'’]{1,40}?\s+largest\s+hubs?\b",
    re.IGNORECASE,
)
_BODY_GEO_EU_REMOTE = re.compile(
    r"\b(?:eu|europe)\s*[-–]\s*remote\b|\bremote\s*[-–]\s*(?:eu|europe)\b",
    re.IGNORECASE,
)
# LATAM / Latin America hiring-region declaration in JD top — nearshore
# outsourcing class. Pattern matches "Location: LATAM (Remote)" / "based in
# Latin America" / "LATAM-Remote". Excludes incidental mentions like "we serve
# clients in the US, EU, and LATAM" by requiring location-context tokens.
_BODY_GEO_LATAM = re.compile(
    r"(?:"
    r"\blocation\s*:?\s*latam\b|"
    r"\blatam\s*\(\s*remote\s*\)|"
    r"\blatam\s*[-–]\s*remote\b|"
    r"\bremote\s*[-–]\s*(?:latam|latin\s+america)\b|"
    r"\bbased\s+in\s+(?:latam|latin\s+america)\b|"
    r"\b(?:must\s+(?:be\s+)?(?:reside|live|located)\s+in)\s+(?:latam|latin\s+america)\b|"
    r"\bcontract\s+role\s+based\s+in\s+(?:latam|latin\s+america)\b"
    r")",
    re.IGNORECASE,
)
# Contract / staff-aug duration framing in JD top. Pattern matches
# "Duration: 6+ months" / "Contract: 12 months W2" — these signal not-direct-
# employment regardless of where the role is geographically. Excludes
# "6 month onboarding period" / "6 months PIP probation" by requiring the
# explicit "duration" or "contract:" header token.
_BODY_CONTRACT_DURATION = re.compile(
    r"\b(?:duration|contract)\s*:?\s*\d+\s*\+?\s*(?:months?|years?)\b",
    re.IGNORECASE,
)
# Hourly-rate comp band in JD body. Pattern captures both single-rate
# ("$45.00/hr") and range ("$34.25 - $49.00 hourly") forms. Annualized at
# 2080 hrs/yr; ceiling below Wei's $110k floor → skip. Excludes contractor /
# 1099 rate ranges via the same-body parse; comp_ok already gates on
# min_amount/max_amount when those structured fields are populated, so this
# only fires when JD body is the sole comp signal. Comp floor logic chosen
# vs. ceiling because LinkedIn often shows max-end of band to drive clicks;
# annualized ceiling < floor is unambiguous skip.
_BODY_HOURLY_COMP_RANGE = re.compile(
    r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:[-–—to]+|to)\s*\$\s*(\d+(?:\.\d{1,2})?)"
    r"\s*(?:hourly|/\s*hour|per\s+hour|/\s*hr|an?\s+hour)",
    re.IGNORECASE,
)
_BODY_HOURLY_COMP_SINGLE = re.compile(
    r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:hourly|/\s*hour|per\s+hour|/\s*hr|an?\s+hour)",
    re.IGNORECASE,
)
# Hourly-rate annualized floor from profile comp.hourly_annual_floor_usd.
def _hourly_comp_floor_per_hr() -> float:
    return comp_settings()['hourly_annual_floor_usd'] / 2080


def has_low_hourly_comp(desc) -> bool:
    """JD body declares an hourly rate whose annualized ceiling < $110k floor.

    Scans the FULL description (unescape'd) — comp/pay-transparency blocks
    are typically at the BOTTOM of LinkedIn JDs, past the 5000-char prose
    cap used by `has_desc_blocker`. Range form (`$34.25 - $49.00 hourly`):
    annualize the high end. Single rate (`$45/hr`): annualize that value.
    Idempotent: returns False if no hourly rate present (comp_ok stays in
    charge for structured min/max_amount fields). Accepts both pre-unescape'd
    desc and already-unescaped strings (idempotent unescape).
    """
    if desc is None or (isinstance(desc, float) and pd.isna(desc)):
        return False
    full = _unescape_jd_body(str(desc).lower())
    m = _BODY_HOURLY_COMP_RANGE.search(full)
    if m:
        try:
            high = float(m.group(2))
            return high < _hourly_comp_floor_per_hr()
        except ValueError:
            return False
    m = _BODY_HOURLY_COMP_SINGLE.search(full)
    if m:
        try:
            rate = float(m.group(1))
            return rate < _hourly_comp_floor_per_hr()
        except ValueError:
            return False
    return False


# Gaming-stack wheelhouse-miss detector (Patch 2026-05-15 per Wei feedback).
# Netflix Games Platform Quality + similar moonshot roles stack 5-10 distinct
# game-engine / embedded-device tokens as required quals. Wei's domain is
# healthcare/fintech/SaaS — pursuing these requires either a referral or a
# moonshot path Wei has explicitly opted into. Default behavior is skip when
# 3+ DISTINCT tokens appear in the first 5000 chars of the JD body, which
# requires deliberate stacking and excludes incidental single mentions of
# e.g. "WebGL" in a healthcare imaging role.
_BODY_GAMING_STACK = re.compile(
    r"\b(?:"
    r"unity3?d?|unreal\s+engine|unreal\b|webgl|webgpu|webassembly|"
    r"game\s+engines?|game\s+studios?|game\s+developers?|"
    r"smart\s+tvs?|streaming\s+sticks?|set[-\s]?top\s+box(?:es)?|"
    r"device\s+farms?|real\s+device\s+orchestration|"
    r"frame\s+cadence|render\s+fidelity|game\s+performance|"
    r"consumer\s+electronics\s+devices?|"
    r"embedded\s+(?:devices?|electronics?|platforms?)|"
    r"defold|pixijs|rive\b"
    r")\b",
    re.IGNORECASE,
)


def has_gaming_wheelhouse_miss(d: str) -> bool:
    """True if JD body has 3+ DISTINCT gaming-stack tokens in first 5000 chars.

    Threshold of 3 distinct tokens chosen to avoid false-positives on
    healthcare/fintech roles that incidentally mention one or two adjacent
    technologies (e.g. medical imaging mentioning "WebGL" once). Stacked
    requirements (game engines + WebGL + device farm + frame cadence) are
    the signature of moonshot-platform roles outside Wei's wheelhouse.
    """
    if not d:
        return False
    head = d[:5000]
    matches = _BODY_GAMING_STACK.findall(head)
    distinct = {m.lower().strip() for m in matches}
    return len(distinct) >= 3
# Outlier-family reposter signature: JD body introduces "Outlier" / "Outlier AI"
# as the operating company (data-labeling gig-work pattern). Adversarially
# verified: legitimate eval roles at known AI labs (Anthropic, OpenAI, Scale,
# Anthropic, Cohere, Databricks, etc.) mention Outlier only in passing, never
# open with "Outlier is at the forefront / Outlier helps ...".
_BODY_OUTLIER_REPOSTER = re.compile(
    r"\boutlier(?:\s+ai)?\s+"
    r"(?:is\s+at\s+the\s+forefront|"
    r"helps\s+(?:the\s+world['']?s?|companies|the\s+most))",
    re.IGNORECASE,
)


# STRICT US-remote test used by has_body_geo_or_reposter_blocker.
# _JD_REMOTE_US (used by passes_wei_geo_and_work_mode) matches loose tokens
# like "fully remote" / "100% remote" / "remote working" without requiring a
# US qualifier nearby — but a JD saying "fully remote work model in india" is
# NOT a US-remote claim. The strict variant requires an explicit US / USA /
# United States / North America token next to (or near) the remote token.
# Used ONLY by the body-geo override; the loose form remains in
# passes_wei_geo_and_work_mode where the location column carries US context.
_JD_REMOTE_US_STRICT = re.compile(
    r'(?:'
    r'\bremote\s*,?\s*(?:us|u\.s\.?|united states|usa|north america)\b'
    r'|\b(?:us|u\.s\.?|united states|usa)[-\s]+remote\b'
    r'|\bremote\s+within\s+(?:the\s+)?(?:u\.?s\.?a\.?|united states)\b'
    r'|\bwork\s+from\s+anywhere\s+(?:in\s+)?(?:the\s+)?(?:u\.?s\.?|united states)\b'
    r'|\bremote\s*,?\s*continental\s+us\b'
    r'|\bremote\s*\(?\s*(?:only\s*,?\s*)?(?:us|u\.s\.?|united states)\s*\)?\b'
    r'|\b(?:us|u\.s\.)\s*[-–]\s*remote\b'
    r'|\bremote\s+(?:eligible|available)\s+(?:for|to)\s+(?:all\s+)?(?:u\.?s\.?|united states)\b'
    r'|\banywhere\s+in\s+the\s+(?:u\.?s\.?a\.?|united states)\b'
    r')',
    re.IGNORECASE,
)


def has_body_geo_or_reposter_blocker(d) -> bool:
    """JD-body role-geo + gig-labeling reposter detector.

    Operates on the first 1500 chars of an already-lowercased, already-unescaped
    description (cheaper + reduces false-positives from distant boilerplate).
    Returns True if:
      • Body opens with an Outlier-family operating-company introduction, OR
      • Body declares India a primary hub AND JD does not make an EXPLICIT
        US-remote claim (strict-token form), OR
      • Body declares EU/Europe-Remote framing AND no explicit US-remote claim.

    Why strict-token US check (vs. _JD_REMOTE_US): a JD that says "India is
    one of our largest hubs" and elsewhere says "fully remote work model in
    india" is not a US-remote role; the loose remote regex matches "fully
    remote" without a US qualifier and would incorrectly escape the geo
    blocker.
    """
    if not d:
        return False
    head = d[:1500]
    if _BODY_OUTLIER_REPOSTER.search(head):
        return True
    # Contract-duration framing fires regardless of remote-US claim — Wei's
    # filter is "direct-employee only", so "Duration: 12+ months" = skip even
    # if the role is technically US-remote.
    if _BODY_CONTRACT_DURATION.search(head):
        return True
    # India / EU / LATAM clauses fire only if JD makes no EXPLICIT US-remote claim.
    has_strict_us_remote = bool(_JD_REMOTE_US_STRICT.search(d))
    if has_strict_us_remote:
        return False
    if _BODY_GEO_INDIA_HUB.search(head):
        return True
    if _BODY_GEO_EU_REMOTE.search(head):
        return True
    if _BODY_GEO_LATAM.search(head):
        return True
    return False

def has_pe(desc) -> bool:
    if not desc or isinstance(desc, float):
        return False
    # Patch 5b: unescape LinkedIn-escaped punctuation so prose regexes match.
    d = _unescape_jd_body(str(desc)[:5000].lower())
    return any(p in d for p in _PE_SIGNALS)

def comp_ok(mn, mx) -> bool:
    """Pass if comp unlisted, ceiling >= profile min_ceiling, or floor >= profile min_floor."""
    thresholds = comp_settings()
    try:
        mn = float(mn) if mn is not None and str(mn) not in ('nan','None','') else None
        mx = float(mx) if mx is not None and str(mx) not in ('nan','None','') else None
    except (ValueError, TypeError):
        mn = mx = None
    if mn is None and mx is None:
        return True
    if mx is not None and mx >= thresholds['min_ceiling_usd']:
        return True
    if mn is not None and mn >= thresholds['min_floor_usd']:
        return True
    return False

def is_us_remote(loc) -> bool:
    """
    True  → keep (confirmed US / remote / ambiguous null)
    False → drop (confirmed international OR unknown explicit location)

    Logic:
      1. None / NaN / empty string → pass (Track L/AS/GH often omit location for remote roles)
      2. Hard international keyword → drop regardless of 'remote' also appearing
      3. Positive US/remote signal → pass
      4. Unknown explicit location → DROP (changed from pass; _INTL_HARD is now comprehensive
         enough that any unknown string is more likely international than US)
    """
    if loc is None or isinstance(loc, float):
        return True
    l = str(loc).strip()
    if not l:
        return True                          # empty → pass (remote role, no location given)
    if _INTL_HARD.search(l):
        return False                         # "Remote - Canada", "Bangalore, India" → drop
    if _US_GEO.search(l):
        return True                          # "Atlanta, GA", "Remote US", "New York" → keep
    return False                             # "Prague", "Lima" (if not in INTL_HARD) → drop

# ── Wei home-geo: JD remote/hybrid + ATL metro (~25mi of 30317) ───────────────
# Zip 30317 (East Atlanta / Reynoldstown). Allowlist = common ITP + inner OTP
# towns within ~25 road miles (heuristic text match — not geodesic).
_JD_DESC_SCAN_LIMIT = 25_000

_JD_REMOTE_US = re.compile(
    r'(?:'
    r'#?\s*li[-\s]?remote\b'
    r'|\b100\s*%\s*remote\b|\bfully\s*remote\b|\bcompletely\s*remote\b|\ball[-\s]?remote\b'
    r'|\bremote[-\s]+(?:first|only|position|role|job)\b'
    r'|\bremote\s+working\b'
    r'|\bremote\s*,?\s*(?:us|u\.s\.?|united states|usa|north america)\b'
    r'|\b(?:us|u\.s\.?|united states|usa)[-\s]+remote\b'
    r'|\bremote\s+within\s+(?:the\s+)?(?:u\.?s\.?a\.?|united states)\b'
    r'|\bwork\s+from\s+anywhere\s+(?:in\s+)?(?:the\s+)?(?:u\.?s\.?|united states)\b'
    r'|\bwork\s+from\s+home\b(?=[^.]{0,120}\b(?:u\.?s\.?|united states|usa)\b)'
    r'|\bwfh\b(?=[^.]{0,120}\b(?:u\.?s\.?|united states|usa)\b)'
    r'|\bremote\s*,?\s*continental\s+us\b'
    r'|\bremote\s*\(?\s*(?:only\s*,?\s*)?(?:us|u\.s\.?|united states)\s*\)?\b'
    r'|\b(?:us|u\.s\.)\s*[-–]\s*remote\b'
    r'|\bremote\s+(?:eligible|available)\s+(?:for|to)\s+(?:all\s+)?(?:u\.?s\.?|united states)\b'
    r'|\banywhere\s+in\s+the\s+(?:u\.?s\.?a\.?|united states)\b'
    r')',
    re.IGNORECASE,
)

_REMOTE_CA_ONLY = re.compile(
    r'(?:canada\s*only|remote\s*\(?\s*canada|must\s+(?:reside|live|be\s+located)\s+in\s+canada'
    r'|based\s+in\s+canada(?!\s*\(.*?us))',
    re.IGNORECASE,
)

_JD_HYBRID_ONSITE = re.compile(
    r'(?:'
    r'\bhybrid\b'
    r'|\b(?:one|two|three|four|five|\d)\s*days?\s*(?:/|\s+per\s+)?\s*week\s*(?:in\s+)?(?:the\s+)?office'
    r'|\b\d+\s*days?\s*(?:/|\s+per\s+)?\s*week\s+on[-\s]?site'
    r'|\bon[-\s]?site\b|\bin[-\s]?person\b'
    r'|\boffice\s*days?\b|\breturn\s+to\s+office\b|\brto\b'
    r'|\b(?:\d|one|two|three)\s*days?\s+on[-\s]?site\b'
    r')',
    re.IGNORECASE,
)

# ── JD body unescape (Patch 5b: 20260515 LinkedIn escape regression) ──
# LinkedIn-sourced JDs in jobspy CSVs contain backslash-escaped punctuation
# (e.g. "on\-site requirement", "$110,000\.00", "U\.S\." citizen), which
# silently defeats every plain-prose regex in this module that uses a
# literal hyphen or period. Symptoms seen on 20260515 batch:
#   • Potawatomi Federal "Location: Rockville, MD (on\-site requirement)"
#     bypassed _JD_HYBRID_ONSITE → triage verdict=apply.
#   • Comp-band parsers (m/d.dd) underreported salaries.
# Mitigation: unescape `\X` → `X` for the common punctuation Wei's filters
# look for, in a fixed cap-length window. Only adds matches (never removes),
# so this is monotonically safer than the un-unescaped baseline.
_JD_ESCAPE_RE = re.compile(r'\\([-.,+%:;()])')


def _unescape_jd_body(d: str) -> str:
    """Strip LinkedIn's backslash-escaping of common punctuation.

    Idempotent on already-unescaped text. Operates on already-lowercased
    string for callers that pre-lower; the underlying replacement is
    case-insensitive.
    """
    if not d:
        return d
    return _JD_ESCAPE_RE.sub(r'\1', d)


def passes_wei_geo_and_work_mode(desc, loc) -> bool:
    """
    US-remote vs hybrid/onsite per JD text + ATL-metro allowlist (~25mi of 30317).

    Order:
      1. Canada-only remote → drop.
      2. JD claims US-remote → keep.
      3. JD claims hybrid/onsite → keep only if ATL allowlist hits JD or location.
      4. Else: if location names a non-ATL office hub and does not say 'remote' → drop.
      5. Else: if location column is empty AND JD silent on remote → drop (# FIX-2026-05-17-LUMA).
         Empty-location is overwhelmingly an indexing artifact on hybrid/intl
         postings (Luma SF/UK case 2026-05-17). Empirical: 7-day scan showed
         0.8% false-negative rate on total daily volume.
      6. Else → keep (defer to is_us_remote for intl vs US).
    """
    if desc is None or (isinstance(desc, float) and pd.isna(desc)):
        d = ''
    else:
        d = _unescape_jd_body(str(desc)[:_JD_DESC_SCAN_LIMIT].lower())

    loc_s = ''
    if loc is not None and not (isinstance(loc, float) and pd.isna(loc)):
        loc_s = str(loc).strip().lower()

    blob = f'{d}\n{loc_s}'

    if _REMOTE_CA_ONLY.search(d):
        return False

    if _JD_REMOTE_US.search(d):
        return True

    pref = remote_preference()
    home_re = home_metro_regex()
    hub_re = silent_office_hubs_regex()

    if _JD_HYBRID_ONSITE.search(d):
        if pref == 'fully_remote':
            return False
        return bool(home_re.search(blob))

    if pref != 'any_us_remote':
        if loc_s and 'remote' not in loc_s and hub_re.search(loc_s):
            if not home_re.search(loc_s):
                return False
        if not loc_s and pref == 'hybrid_home_metro':
            return False

    return True


def l1_pipeline_fail_rule(
    company: object,
    title: object,
    desc: object,
    location: object,
    min_amount: object,
    max_amount: object,
) -> str:
    """First L1 filter failure, or '' if the row would pass the scrape pipeline."""
    company_s = '' if company is None else str(company)
    title_s = '' if title is None else str(title)
    loc_s = '' if location is None else str(location)
    if is_skip_company(company_s):
        return 'skip_company'
    if is_skip_title_company_signal(title_s):
        return 'skip_title_company_signal'
    if has_title_blocker(title_s):
        return 'title_blocker'
    if not has_required_signal(title_s):
        return 'missing_title_required_signal'
    if has_pe(desc):
        return 'pe_signal_in_jd'
    if not comp_ok(min_amount, max_amount):
        return 'comp_below_threshold'
    if has_desc_blocker(desc):
        return 'desc_blocker'
    if not is_us_remote(loc_s):
        return 'non_us_remote_location'
    if not passes_wei_geo_and_work_mode(desc, loc_s):
        return 'geo_or_work_mode'
    return ''


# ── Scraper helpers ────────────────────────────────────────────────────────────
_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}


def _http_get_with_retries(
    url: str,
    *,
    params: dict | None = None,
    timeout: float = 30.0,
    tag: str = 'http',
) -> requests.Response:
    """GET with backoff on timeouts, connection errors, and transient 502/503/504."""
    delays = (1.0, 2.5, 5.0)
    last_resp: requests.Response | None = None
    for attempt, delay in enumerate(delays, start=1):
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
            last_resp = resp
            if resp.status_code in (502, 503, 504) and attempt < len(delays):
                logging.warning(
                    '%s: HTTP %s %s (attempt %s/%s)', tag, resp.status_code, url, attempt, len(delays)
                )
                time.sleep(delay)
                continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            logging.warning('%s: %s %s (attempt %s/%s)', tag, exc, url, attempt, len(delays))
            if attempt < len(delays):
                time.sleep(delay)
                continue
            raise
    assert last_resp is not None
    return last_resp


def _age_days(date_str: str) -> int:
    """Return how many days ago an ISO8601 date string was."""
    try:
        return (datetime.now(timezone.utc) -
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))).days
    except Exception:
        return 999


# ── Track R: Remotive public API ──────────────────────────────────────────────
REMOTIVE_SEARCHES = [
    # QA / SDET / Eval
    'SDET', 'evaluation engineer', 'quality engineer',
    'LLM evaluation', 'AI quality', 'software engineer in test',
    'test automation engineer', 'QA automation',
    # PM / TPM (Remotive skews toward remote-first startups — good PM signal)
    'technical program manager', 'AI product manager',
    'product owner', 'technical product manager',
]

def scrape_remotive() -> pd.DataFrame:
    rows, seen = [], set()
    base = 'https://remotive.com/api/remote-jobs'
    for term in REMOTIVE_SEARCHES:
        print(f'[Track R] remotive: {term}')
        try:
            resp = _http_get_with_retries(
                base,
                params={'category': 'software-dev', 'search': term, 'limit': 50},
                timeout=20.0,
                tag=f'remotive:{term[:24]}',
            )
            resp.raise_for_status()
            for j in resp.json().get('jobs', []):
                url = j.get('url', '')
                if not url or url in seen:
                    continue
                seen.add(url)
                if _age_days(j.get('publication_date', '')) > 14:
                    continue
                rows.append({
                    'track':      'R',
                    'title':      j.get('title', ''),         # title only, not prepending type
                    'company':    j.get('company_name', ''),
                    'location':   j.get('candidate_required_location', 'Remote'),
                    'date_posted': j.get('publication_date', '')[:10],
                    'min_amount': None,
                    'max_amount': None,
                    'job_url':    url,
                    'description': strip_html(j.get('description', '')),  # strip HTML
                    'query':      term,
                })
            raw_count = len(resp.json().get('jobs', []))
            kept = sum(1 for r in rows if r["query"]==term)
            print(f'  → {raw_count} raw, {kept} kept (≤14d, signal title)')
        except Exception as exc:
            logging.warning('remotive %s: %s', term, exc)
            print(f'  ERROR: {exc}')
        time.sleep(1)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Track L: Lever public API ─────────────────────────────────────────────────
# Official public API — no auth required.
# Docs: https://github.com/lever/postings-api
def scrape_lever() -> pd.DataFrame:
    rows = []
    for co in LEVER_COMPANIES:
        print(f'[Track L] lever: {co}')
        try:
            resp = _http_get_with_retries(
                f'https://api.lever.co/v0/postings/{co}',
                params={'mode': 'json'},
                timeout=25.0,
                tag=f'lever:{co}',
            )
            if resp.status_code == 404:
                print(f'  → 404 (company not on Lever or slug wrong)')
                continue
            resp.raise_for_status()
            postings = resp.json()
            found = 0
            for p in postings:
                title = p.get('text', '')
                if not has_required_signal(title) or has_title_blocker(title):
                    continue
                cats = p.get('categories', {})
                location = cats.get('location', '') or cats.get('allLocations', [''])[0] if cats.get('allLocations') else ''
                # Lever salaryRange is optional; structure: {min, max, currency, interval}
                sal = p.get('salaryRange') or {}
                mn = sal.get('min') if sal else None
                mx = sal.get('max') if sal else None
                # Annualise if interval is hourly (rare but possible)
                if sal.get('interval') == 'per-hour-paid':
                    mn = mn * 2080 if mn else None
                    mx = mx * 2080 if mx else None
                desc_raw = p.get('descriptionPlain') or strip_html(p.get('description', ''))
                rows.append({
                    'track':      'L',
                    'title':      title,
                    'company':    co,
                    'location':   location or 'Remote',
                    'date_posted': datetime.fromtimestamp(
                        p['createdAt'] / 1000, tz=timezone.utc
                    ).strftime('%Y-%m-%d') if p.get('createdAt') else None,
                    'min_amount': mn,
                    'max_amount': mx,
                    'job_url':    p.get('hostedUrl', ''),
                    'description': desc_raw[:5000],
                    'query':      f'lever:{co}',
                })
                found += 1
            print(f'  → {len(postings)} total postings, {found} signal roles')
        except Exception as exc:
            logging.warning('lever %s: %s', co, exc)
            print(f'  ERROR: {exc}')
        time.sleep(1)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Track AS: Ashby public API ────────────────────────────────────────────────
# Official public API — no auth required.
# Docs: https://developers.ashbyhq.com/docs/public-job-posting-api
def scrape_ashby() -> pd.DataFrame:
    rows = []
    for co in ASHBY_COMPANIES:
        print(f'[Track AS] ashby: {co}')
        try:
            resp = _http_get_with_retries(
                f'https://api.ashbyhq.com/posting-api/job-board/{co}',
                params={'includeCompensation': 'true'},
                timeout=45.0,
                tag=f'ashby:{co}',
            )
            if resp.status_code == 404:
                print(f'  → 404 (company not on Ashby or slug wrong)')
                continue
            resp.raise_for_status()
            data = resp.json()
            postings = data.get('jobPostings', [])
            found = 0
            for p in postings:
                title = p.get('title', '')
                if not has_required_signal(title) or has_title_blocker(title):
                    continue
                # Ashby compensation: {summaryComponents: [{...}], compensationTierSummary}
                comp = p.get('compensationTierSummary', '') or ''
                # Try to parse structured comp if available
                mn = mx = None
                for tier in p.get('compensation', {}).get('summaryComponents', []):
                    if tier.get('type') == 'SalaryRange':
                        mn = tier.get('min')
                        mx = tier.get('max')
                        break
                loc_parts = [l.get('name', '') for l in p.get('jobLocation', [])] if p.get('jobLocation') else []
                location = ', '.join(loc_parts) if loc_parts else p.get('isRemote', False) and 'Remote' or ''
                rows.append({
                    'track':      'AS',
                    'title':      title,
                    'company':    co,
                    'location':   location or 'Remote',
                    'date_posted': p.get('publishedDate', '')[:10] if p.get('publishedDate') else None,
                    'min_amount': mn,
                    'max_amount': mx,
                    'job_url':    p.get('jobUrl', ''),
                    'description': strip_html(p.get('descriptionHtml', '') or p.get('descriptionPlain', '')),
                    'query':      f'ashby:{co}',
                })
                found += 1
            print(f'  → {len(postings)} total postings, {found} signal roles')
        except Exception as exc:
            logging.warning('ashby %s: %s', co, exc)
            print(f'  ERROR: {exc}')
        time.sleep(1)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Track GH: Greenhouse company boards (HTML parse) ─────────────────────────
def scrape_greenhouse_boards() -> pd.DataFrame:
    rows = []
    for co in GREENHOUSE_COMPANIES:
        url = f'https://job-boards.greenhouse.io/{co}'
        print(f'[Track GH] greenhouse: {co}')
        try:
            resp = _http_get_with_retries(url, timeout=25.0, tag=f'gh:{co}')
            if resp.status_code != 200:
                print(f'  → {resp.status_code}, skipping')
                continue
            parser = _GHJobParser()
            parser.feed(resp.text)
            found = skipped_intl = 0
            for raw_title, raw_location, href in parser.jobs:
                # Repair Dialpad-style concatenations: "Sr. SDETKitchener, Canada"
                title, location = _split_gh_title_location(raw_title, raw_location)
                if not has_required_signal(title) or has_title_blocker(title):
                    continue
                if not is_us_remote(location or None):
                    skipped_intl += 1
                    continue
                job_url = href if href.startswith('http') else f'https://job-boards.greenhouse.io{href}'
                rows.append({
                    'track':      'GH',
                    'title':      title,
                    'company':    co,
                    'location':   location or 'Remote (verify)',
                    'date_posted': None,
                    'min_amount': None,
                    'max_amount': None,
                    'job_url':    job_url,
                    'description': '',
                    'query':      f'greenhouse:{co}',
                })
                found += 1
            note = f', {skipped_intl} intl filtered' if skipped_intl else ''
            print(f'  → {found} signal roles{note}')
        except Exception as exc:
            logging.warning('greenhouse %s: %s', co, exc)
            print(f'  ERROR: {exc}')
        time.sleep(1)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Yield / funnel logs ───────────────────────────────────────────────────────
# yield_log.csv      — legacy 6-column rollup (kept for quick spreadsheets).
# yield_funnel.csv   — extended funnel incl. PE/comp, desc, US col vs JD geo.
YIELD_LOG    = os.path.join(OUT_DIR, 'yield_log.csv')
YIELD_FUNNEL = os.path.join(OUT_DIR, 'yield_funnel.csv')


def _append_yield(
    raw: int,
    after_skip: int,
    after_blockers: int,
    after_whitelist: int,
    after_pe_comp: int,
    after_desc: int,
    after_us_remote: int,
    after_wei_geo: int,
    final: int,
) -> None:
    """Append one row to legacy yield_log + detailed yield_funnel."""
    legacy_header = not os.path.exists(YIELD_LOG)
    with open(YIELD_LOG, 'a') as f:
        if legacy_header:
            f.write('date,raw_deduped,after_skip,after_title_blockers,'
                    'after_title_whitelist,final\n')
        f.write(f'{DATESTAMP},{raw},{after_skip},{after_blockers},'
                f'{after_whitelist},{final}\n')

    funnel_header = not os.path.exists(YIELD_FUNNEL)
    with open(YIELD_FUNNEL, 'a') as f:
        if funnel_header:
            f.write(
                'date,raw_deduped,after_skip,after_title_blockers,'
                'after_title_whitelist,after_pe_comp,after_desc,'
                'after_us_remote_col,after_jd_geo_workmode,final\n'
            )
        f.write(
            f'{DATESTAMP},{raw},{after_skip},{after_blockers},'
            f'{after_whitelist},{after_pe_comp},{after_desc},'
            f'{after_us_remote},{after_wei_geo},{final}\n'
        )

    print(
        f'[yield] {DATESTAMP}: {raw}→{after_skip}→{after_blockers}'
        f'→{after_whitelist}→{after_pe_comp}→{after_desc}'
        f'→us_col={after_us_remote}→jd_geo={after_wei_geo}→{final}'
    )
    print(f'  legacy: {YIELD_LOG}  funnel: {YIELD_FUNNEL}')


# ── New company discovery ──────────────────────────────────────────────────────
# After filtering, detect result companies using Ashby/GH/Lever that aren't in
# the tracked lists yet. Print them as suggestions for extra_*.txt files.
def _suggest_new_companies(result_df: pd.DataFrame) -> None:
    def _slug(s: str) -> str:
        return re.sub(r'[\s\-\.]', '', s.lower())

    tracked_slugs = (
        {_slug(c) for c in ASHBY_COMPANIES}
        | {_slug(c) for c in GREENHOUSE_COMPANIES}
        | {_slug(c) for c in LEVER_COMPANIES}
    )
    suggestions: dict[str, str] = {}
    for _, row in result_df.iterrows():
        co = str(row.get('company', '')).strip()
        if not co or _slug(co) in tracked_slugs:
            continue
        url = str(row.get('job_url', ''))
        if 'ashbyhq.com' in url:
            ats = 'ASHBY   → extra_ashby.txt'
        elif 'greenhouse.io' in url:
            ats = 'GH      → extra_gh.txt'
        elif 'lever.co' in url:
            ats = 'LEVER   → extra_lever.txt'
        else:
            continue
        if co not in suggestions:
            suggestions[co] = ats
    if suggestions:
        print('\n── New companies detected (not yet tracked) ─────────────────────────')
        for co, ats in sorted(suggestions.items(), key=lambda x: (x[1], x[0])):
            print(f'  {ats}: {co}')
        print('─────────────────────────────────────────────────────────────────────')


def main() -> None:
    # ══════════════════════════════════════════════════════════════════════════════
    # MAIN SCRAPE
    # ══════════════════════════════════════════════════════════════════════════════
    all_jobs: list[pd.DataFrame] = []
    tracks_on = enabled_tracks()
    print(f'[tracks] enabled: {", ".join(sorted(tracks_on))}')

    # ── Track A + B + C: Indeed + LinkedIn ───────────────────────────────────────
    _abc_roles: list[tuple[str, str]] = []
    if 'A' in tracks_on:
        _abc_roles.extend(('A', r) for r in TRACK_A)
    if 'B' in tracks_on:
        _abc_roles.extend(('B', r) for r in TRACK_B)
    if 'C' in tracks_on:
        _abc_roles.extend(('C', r) for r in TRACK_C)
    for track, role in _abc_roles:
        print(f'[Track {track}] {role}')
        try:
            jobs = scrape_jobs(
                site_name=['indeed', 'linkedin'],
                search_term=role,
                location='Remote',
                results_wanted=30,
                hours_old=168,
                country_indeed='USA',
                linkedin_fetch_description=True,
            )
            if not jobs.empty:
                jobs['query'] = role
                jobs['track'] = track
                all_jobs.append(jobs)
                print(f'  → {len(jobs)} results')
            else:
                print(f'  → 0')
        except Exception as exc:
            logging.warning('jobspy A/B %s: %s', role, exc)
            print(f'  ERROR: {exc}')
        time.sleep(3)

    # ── Track G: Google Jobs ──────────────────────────────────────────────────────
    for gq in (GOOGLE_QUERIES if 'G' in tracks_on else []):
        print(f'[Track G] {gq}')
        try:
            jobs = scrape_jobs(
                site_name=['google'],
                search_term=gq,
                google_search_term=f'{gq} since past week',
                location='Remote',
                results_wanted=20,
                hours_old=168,
                country_indeed='USA',
            )
            if not jobs.empty:
                jobs['query'] = gq
                jobs['track'] = 'G'
                all_jobs.append(jobs)
                print(f'  → {len(jobs)} results')
            else:
                print(f'  → 0')
        except Exception as exc:
            # Google scraper has has_retry=True in python-jobspy; do not add our own.
            logging.warning(
                'jobspy G query=%r site=google: %s',
                gq, exc, exc_info=True,
            )
            print(f'  ERROR: {type(exc).__name__}: {exc}')
        time.sleep(3)

    # ── Track R: Remotive API ─────────────────────────────────────────────────────
    if 'R' in tracks_on:
        r_df = scrape_remotive()
        if not r_df.empty:
            all_jobs.append(r_df)

    # ── Track L: Lever API ────────────────────────────────────────────────────────
    if 'L' in tracks_on:
        l_df = scrape_lever()
        if not l_df.empty:
            all_jobs.append(l_df)

    # ── Track AS: Ashby API ───────────────────────────────────────────────────────
    if 'AS' in tracks_on:
        as_df = scrape_ashby()
        if not as_df.empty:
            all_jobs.append(as_df)

    # ── Track GH: Greenhouse boards ───────────────────────────────────────────────
    if 'GH' in tracks_on:
        gh_df = scrape_greenhouse_boards()
        if not gh_df.empty:
            all_jobs.append(gh_df)

    if not all_jobs:
        print('\nNo results from any track. Try hours_old=336 (14 days) for A/B/G.')
        sys.exit(0)

    df = pd.concat(all_jobs, ignore_index=True)
    df = df.drop_duplicates(subset=['job_url'])
    # Secondary dedup: same (title, company) within same track = LinkedIn URL dupes of one posting.
    # Keep the row with the most complete location/comp data.
    df = df.sort_values(['min_amount', 'max_amount', 'location'], ascending=False, na_position='last')
    df = df.drop_duplicates(subset=['title', 'company', 'track'], keep='first')
    _n_raw = len(df)
    print(f'\nRaw deduplicated: {_n_raw}')

    # ══════════════════════════════════════════════════════════════════════════════
    # FILTER PIPELINE (annotate all rows; do not drop — human audit + L2 triage)
    # ══════════════════════════════════════════════════════════════════════════════
    df = add_prescreen_columns(df)
    df['screening_company_skip'] = df['company'].apply(is_skip_company)
    df['screening_skip_key'] = df['company'].apply(
        lambda c: skip_company_match_key(c) or ''
    )
    df['l1_pipeline_fail_rule'] = df.apply(
        lambda r: l1_pipeline_fail_rule(
            r.get('company'),
            r.get('title'),
            r.get('description'),
            r.get('location'),
            r.get('min_amount'),
            r.get('max_amount'),
        ),
        axis=1,
    )
    df['l1_pipeline_pass'] = df['l1_pipeline_fail_rule'].eq('')

    # Funnel counts: cumulative masks (same semantics as legacy drop pipeline).
    m_co = ~df['company'].apply(is_skip_company)
    m_title_sig = m_co & ~df['title'].apply(is_skip_title_company_signal)
    m_blockers = m_title_sig & ~df['title'].apply(has_title_blocker)
    m_whitelist = m_blockers & df['title'].apply(has_required_signal)
    m_pe = m_whitelist & ~df.apply(lambda r: has_pe(r.get('description')), axis=1)
    m_comp = m_pe & df.apply(
        lambda r: comp_ok(r.get('min_amount'), r.get('max_amount')), axis=1,
    )
    m_desc = m_comp & ~df.apply(lambda r: has_desc_blocker(r.get('description')), axis=1)
    m_us = m_desc & df['location'].map(is_us_remote)
    m_geo = m_us & df.apply(
        lambda r: passes_wei_geo_and_work_mode(r.get('description'), r['location']),
        axis=1,
    )
    _n_skip = int(m_co.sum())
    _n_blockers = int(m_blockers.sum())
    _n_whitelist = int(m_whitelist.sum())
    _n_pe_comp = int(m_comp.sum())
    _n_desc = int(m_desc.sum())
    _n_us_remote = int(m_us.sum())
    _n_wei_geo = int(m_geo.sum())
    _n_final = int(m_geo.sum())

    print(f'After company skip:     {_n_skip}')
    print(f'After title company signals: {int(m_title_sig.sum())}')
    print(f'After title blockers:   {_n_blockers}')
    print(f'After title whitelist:  {_n_whitelist}')
    print(f'After PE + comp:        {_n_pe_comp}')
    print(f'After desc blockers:    {_n_desc}')
    print(f'After US location col:  {_n_us_remote}')
    print(f'After JD work-mode (ATL hybrid):  {_n_wei_geo}')

    # ── Save ──────────────────────────────────────────────────────────────────────
    cols = [
        'track', 'title', 'company', 'location', 'date_posted',
        'min_amount', 'max_amount', 'priority', 'stack_hits', 'yrs_req',
        'domain', 'funding', 'job_url', 'description', 'query',
        'screening_company_skip', 'screening_skip_key',
        'l1_pipeline_pass', 'l1_pipeline_fail_rule',
    ]
    available_cols = [c for c in cols if c in df.columns]
    _seen_urls = load_seen_job_urls(OUT_DIR, os.path.basename(OUT_CSV))
    _url_key = df['job_url'].map(normalize_job_url)
    _new_mask = _url_key.ne('') & ~_url_key.isin(_seen_urls)
    _new_df = df.loc[_new_mask]
    _n_new = len(_new_df)

    df[available_cols].to_csv(OUT_CSV, index=False)
    _new_df[available_cols].to_csv(OUT_NEW, index=False)

    # ── Summary ───────────────────────────────────────────────────────────────────
    print(f'\n{"="*60}')
    print(
        f'RESULTS: {len(df)} rows in CSV ({_n_final} pass L1 pipeline; '
        f'{int(df["screening_company_skip"].sum())} company-skip for audit)'
    )
    print(f'Saved:  {OUT_CSV}')
    print(f'Net new (URLs not in prior jobspy_results_*.csv): {_n_new}  ->  {OUT_NEW}')
    if os.path.getsize(ERR_LOG) > 0:
        print(f'Errors: {ERR_LOG}')
    print('='*60)
    disp = ['priority', 'track', 'title', 'company', 'location',
            'date_posted', 'min_amount', 'max_amount', 'stack_hits', 'yrs_req', 'domain', 'funding']
    _pass_df = df[df['l1_pipeline_pass']]
    print(_pass_df[[c for c in disp if c in _pass_df.columns]].to_string())

    # ── Yield log + new company discovery ────────────────────────────────────────
    _append_yield(
        _n_raw,
        _n_skip,
        _n_blockers,
        _n_whitelist,
        _n_pe_comp,
        _n_desc,
        _n_us_remote,
        _n_wei_geo,
        _n_final,
    )
    _suggest_new_companies(_pass_df)


if __name__ == "__main__":
    main()

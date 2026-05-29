"""
test_run_search_locally.py — characterization tests for filter functions.

Run: python3 -m pytest jobspy/test_run_search_locally.py -q

These tests pin CURRENT behavior of the filter functions in run_search_locally.py
so that subsequent refactors (e.g., normalize_company_key + startswith match) can be
verified against a reference. New behavior tests live in matching `test_*` files;
this file only encodes pre-refactor truth.

Scope:
  - is_skip_company, is_skip_title_company_signal
  - has_required_signal, has_title_blocker
  - has_pe, has_desc_blocker
  - comp_ok
  - is_us_remote, passes_wei_geo_and_work_mode
  - normalize_job_url

Side effects on import: run_search_locally.py reads application_index.html and
auto-merges discovered companies into SKIP_COMPANIES. We do not assert on the
exact membership of SKIP_COMPANIES here for that reason; we only test that
known-fixed fictional slugs (acme-corp, zenith-ai, etc.) skip correctly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_JOBSPY_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _JOBSPY_DIR.parent
os.environ.setdefault(
    "QA_JOB_PROFILE",
    str(_REPO_ROOT / "config" / "profile.test.yaml"),
)
sys.path.insert(0, str(_REPO_ROOT / "jobspy"))
sys.path.insert(0, str(_REPO_ROOT / "applications"))
sys.path.insert(0, str(_JOBSPY_DIR))

import run_search_locally as rsl  # noqa: E402


# ── is_skip_company ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "Acme Corp",
    "acme-corp",
    "Acme Corp Inc.",
    "Zenith AI",
    "FictoDefense",
    "FictoDefense Industries",
    "Example-Shop.com",
    "exampleshop",
    "Example Outsourcing LLC",
    "Example Staffing LLC",
])
def test_skip_company_known_skip(name: str) -> None:
    assert rsl.is_skip_company(name) is True


@pytest.mark.parametrize("name", [
    "Anthropic",
    "Stripe",
    "Datadog",
    "Linear",
    "Vercel",
    "Notion",
])
def test_skip_company_known_pass(name: str) -> None:
    assert rsl.is_skip_company(name) is False


def test_skip_company_faux_exact_only() -> None:
    # 'faux' is in skip_companies.test.txt; suffix guard must not match 'checkpoint'.
    assert rsl.is_skip_company("Faux") is True
    assert rsl.is_skip_company("Checkpoint Systems") is False


def test_skip_company_andela_not_anderson() -> None:
    """Prefix match must not skip unrelated names (andela vs anderson)."""
    rsl.SKIP_COMPANIES.add('andela')
    rsl.invalidate_default_cache()
    assert rsl.is_skip_company("Andela") is True
    assert rsl.is_skip_company("Anderson Technologies") is False
    rsl.SKIP_COMPANIES.discard('andela')
    rsl.invalidate_default_cache()


def test_skip_company_acme_not_acmechanical() -> None:
    rsl.invalidate_default_cache()
    assert rsl.is_skip_company("Acme Corp") is True
    assert rsl.is_skip_company("Acmechanical Systems") is False


def test_skip_company_example_gov_fictolify_on_list() -> None:
    rsl.invalidate_default_cache()
    assert rsl.is_skip_company("Example Gov LLC") is True
    assert rsl.is_skip_company("Fictolify") is True


def test_skip_company_fictexian_digital_prefix() -> None:
    rsl.invalidate_default_cache()
    assert rsl.is_skip_company("Fictexian Digital") is True


# ── has_required_signal ───────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Senior SDET",
    "Software Engineer in Test",
    "Quality Engineer",
    "QA Engineer",
    "Senior QA Automation Engineer",
    "Quality Lead",
    "QA Lead",
    "Test Engineer",
    "LLM Evaluation Engineer",
    "AI Quality Engineer",
    "Developer Productivity Engineer",
    "Test Infrastructure Engineer",
    "Technical Program Manager",
    "AI Product Manager",
    # 'Product Owner' REMOVED 2026-05-17 to match TITLE_REQUIRED change at
    # run_search_locally.py:461 (Wei feedback 2026-05-15: PO is a senior PM).
])
def test_has_required_signal_positive(title: str) -> None:
    assert rsl.has_required_signal(title) is True


@pytest.mark.parametrize("title", [
    "Software Engineer",
    "Senior Backend Engineer",
    "Frontend Developer",
    "Marketing Manager",
])
def test_has_required_signal_negative(title: str) -> None:
    assert rsl.has_required_signal(title) is False


# ── has_title_blocker ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Java Developer",
    "Data Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "ML Engineer",
    "Forward Deployed Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Backend Engineer",
    "Senior Frontend Engineer",
    "Associate Product Manager",
    "Growth Product Manager",
    "Manufacturing Quality Engineer",
    "Hardware Engineer",
])
def test_has_title_blocker_positive(title: str) -> None:
    assert rsl.has_title_blocker(title) is True


@pytest.mark.parametrize("title", [
    "Senior SDET",
    "Quality Engineer",
    "AI Quality Engineer",
    "Test Automation Engineer",
])
def test_has_title_blocker_negative(title: str) -> None:
    assert rsl.has_title_blocker(title) is False


# ── comp_ok ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mn,mx,expected", [
    (None, None, True),       # both unlisted: pass
    (125_000, 160_000, True),  # ceiling >= profile min_ceiling_usd (125k fixture)
    (105_000, None, True),     # floor >= profile min_floor_usd (105k fixture)
    (None, 125_000, True),     # ceiling >= 125k
    (None, 124_000, False),    # ceiling below 125k AND no floor anchor
    (104_000, 119_000, False),  # floor < 105k AND ceiling < 125k
    (105_000, 119_000, True),  # floor >= 105k branch
    (80_000, 99_000, False),
    ("nan", "nan", True),       # NaN-string treated as unlisted
])
def test_comp_ok_table(mn, mx, expected: bool) -> None:
    assert rsl.comp_ok(mn, mx) is expected


# ── is_us_remote ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("loc,expected", [
    (None, True),
    ("", True),
    ("Remote", True),
    ("Remote, USA", True),
    ("United States", True),
    ("Atlanta, GA", True),
    ("New York, NY", True),
    ("Bangalore, India", False),
    ("Remote - Canada", False),       # intl wins over 'remote'
    ("Toronto", False),
    ("London", False),
    ("Mexico City", False),
    ("Prague", False),                # not in US allowlist
    ("EMEA", False),
    ("Tegucigalpa, Francisco Morazán, USA", False),  # JobSpy USA suffix artifact
    ("Portland, OR, USA", True),
])
def test_is_us_remote_table(loc, expected: bool) -> None:
    assert rsl.is_us_remote(loc) is expected


# ── has_pe ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("desc,expected", [
    ("Backed by Thoma Bravo since 2022.", True),
    ("Vista Equity Partners portfolio company.", True),
    ("Acquired by KKR portfolio in 2024.", True),
    ("We are a Series B startup.", False),
    ("", False),
    (None, False),
])
def test_has_pe_table(desc, expected: bool) -> None:
    assert rsl.has_pe(desc) is expected


# ── has_desc_blocker ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("desc,expected", [
    ("Up to 25% travel required for client visits.", True),
    ("Top secret clearance required.", True),
    ("Master's degree required in Computer Science.", True),
    ("Java required as primary language.", True),
    ("Must be located in India.", True),
    ("Right to work in the EU required.", True),
    # Foreign currency without USD anchor → block
    ("Salary: £80,000 - £100,000 per year.", True),
    # Foreign currency WITH USD anchor → pass
    ("Salary: $130,000 - $160,000 USD; some EU benefits in EUR.", False),
    ("We're a remote-first US company hiring quality engineers.", False),
    ("", False),
])
def test_has_desc_blocker_table(desc, expected: bool) -> None:
    assert rsl.has_desc_blocker(desc) is expected


# ── normalize_job_url ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://example.com/jobs/123", "https://example.com/jobs/123"),
    ("https://example.com/jobs/123/", "https://example.com/jobs/123"),
    ("https://example.com/jobs/123?utm=foo", "https://example.com/jobs/123"),
    ("https://example.com/jobs/123#section", "https://example.com/jobs/123"),
    ("HTTPS://Example.COM/jobs/123", "https://example.com/jobs/123"),
    ("", ""),
    (None, ""),
    ("nan", ""),
])
def test_normalize_job_url_table(url, expected: str) -> None:
    assert rsl.normalize_job_url(url) == expected


# ── passes_wei_geo_and_work_mode (smoke only — full coverage is heavy) ────────

def test_geo_jd_us_remote_passes() -> None:
    desc = "This is a 100% remote position based in the United States."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Remote, USA") is True


def test_geo_jd_canada_only_drops() -> None:
    desc = "Remote (Canada). Must be located in Canada."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Remote, Canada") is False


def test_geo_jd_hybrid_home_metro_passes() -> None:
    desc = "Hybrid 3 days per week in office."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Portland, OR") is True


def test_geo_jd_hybrid_non_home_metro_drops() -> None:
    desc = "Hybrid 3 days per week in office."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Philadelphia, PA") is False


def test_geo_silent_jd_office_hub_drops() -> None:
    # JD doesn't mention remote, location is a non-home hub → drop
    desc = "We are looking for an experienced Quality Engineer to join our team."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Irving, TX") is False


# ── normalize_company_key + post-refactor is_skip_company ─────────────────────
# These tests describe behavior introduced by P0 #2 (consumer-side normalization
# per contract §10). They will fail until normalize_company_key is implemented
# and is_skip_company is rewritten to use startswith on normalized keys.

@pytest.mark.parametrize("raw,expected", [
    ("Acme Corp", "acmecorp"),
    ("Example-Shop.com", "exampleshopcom"),
    ("Apex Systems Inc.", "apexsystemsinc"),
    ("Amp Co & Sons", "ampcosons"),       # ampersand stripped
    ("Amp Co &amp; Sons", "ampcosons"),    # html-entity decoded then stripped
    ("US Tech Solutions", "ustechsolutions"),
    ("Example Outsourcing LLC", "exampleoutsourcingllc"),
    ("E-IT", "eit"),
    ("",  ""),
    (None, ""),
])
def test_normalize_company_key(raw, expected: str) -> None:
    assert rsl.normalize_company_key(raw) == expected


def test_skip_company_fixes_substring_fp_on_rapp() -> None:
    """
    Current substring match: 'rapp' in 'wrapper inc' → True (FALSE POSITIVE).
    Post-refactor: normalize('Wrapper Inc') = 'wrapperinc'; no SKIP key starts a prefix.
    """
    assert rsl.is_skip_company("Wrapper Inc") is False


def test_skip_company_html_entity_aligns_with_jobspy() -> None:
    """
    Auto-skip token from index_companies (per contract §3.2) carries '&amp;' literal.
    JobSpy returns the company as 'Amp Co & Sons'. Post-refactor normalization
    aligns both: both → 'ampcosons'. Substring match could not bridge this gap.
    """
    # Simulate the auto-skip token shape from index_companies:
    raw_token_from_index = "amp co &amp; sons"
    # Both shapes must normalize identically:
    assert rsl.normalize_company_key(raw_token_from_index) == rsl.normalize_company_key("Amp Co & Sons")


# FIX-2026-05-17-LUMA REGRESSION TESTS
# Tests for the three Luma-driven fixes applied 2026-05-17:
#   (A) Master's-in-non-CS-field regex in _DESC_REGEX
#   (B) UX-research substring set in _DESC_PLAIN
#   (C) Empty location + JD silent on remote → drop in passes_wei_geo_and_work_mode

LUMA_DESC = """About Luma AI. Luma's mission is to build multimodal AI. We're seeking a candidate to evaluate models. Qualifications: Master's degree or higher in Cognitive Science, Human-Computer Interaction (HCI), Design Research, Psychology, Media Studies, or a related field. 5+ years of experience in UX research."""


def test_fixA_masters_in_hci_blocked() -> None:
    """Luma JD requires Master's in HCI/Psych/etc — must hit desc blocker."""
    assert rsl.has_desc_blocker(LUMA_DESC) is True


def test_fixA_masters_in_cs_NOT_blocked() -> None:
    """Master's in CS or related engineering should NOT be blocked."""
    desc = "Qualifications: Master's degree in Computer Science or related field."
    assert rsl.has_desc_blocker(desc) is False


def test_fixA_phd_in_psychology_blocked() -> None:
    desc = "We require a PhD in experimental psychology or related field."
    assert rsl.has_desc_blocker(desc) is True


def test_fixB_ux_research_role_blocked() -> None:
    """Bare 'ux research' substring should fire desc blocker."""
    desc = "You'll lead UX research for our generative AI product."
    assert rsl.has_desc_blocker(desc) is True


def test_fixB_qualitative_researcher_blocked() -> None:
    desc = "We're hiring a Qualitative Researcher to evaluate model outputs."
    assert rsl.has_desc_blocker(desc) is True


def test_fixC_empty_loc_silent_jd_dropped() -> None:
    """Luma case: empty location, JD never mentions remote → drop."""
    desc_no_remote_mention = (
        "About the company. We build AI. Responsibilities: evaluate models. "
        "Qualifications: 5+ years experience in product evaluation."
    )
    assert rsl.passes_wei_geo_and_work_mode(desc_no_remote_mention, "") is False


def test_fixC_empty_loc_jd_claims_us_remote_kept() -> None:
    """Empty location but JD says fully remote → still kept (step 2 fires first)."""
    desc = "This is a 100% remote role open to candidates in the United States."
    assert rsl.passes_wei_geo_and_work_mode(desc, "") is True


def test_fixC_nonempty_loc_remote_us_kept() -> None:
    """Regression: 'Remote, US' location string stays valid."""
    desc = "Fully remote position. Work from anywhere in the US."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Remote, US") is True


def test_fixC_home_metro_hybrid_kept() -> None:
    """Regression: home-metro hybrid still passes the profile allowlist."""
    desc = "Hybrid role: 3 days/week in our Portland office."
    assert rsl.passes_wei_geo_and_work_mode(desc, "Portland, OR") is True


def test_fixC_luma_combined_filter_chain() -> None:
    """End-to-end: Luma's exact shape must be rejected by combined filters."""
    assert rsl.has_desc_blocker(LUMA_DESC) is True
    # And the geo check on empty loc would also drop it
    assert rsl.passes_wei_geo_and_work_mode(LUMA_DESC, "") is False

#!/usr/bin/env bash
# Interactive onboarding for QA-Job-Script (macOS/Linux).
# Idempotent: safe to re-run; skips files that already exist.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

step() {
  echo ""
  echo "==> $1"
}

warn() {
  echo "WARNING: $1" >&2
}

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [[ -f "$dest" ]]; then
    echo "  keep  $dest (already exists)"
  else
    cp "$src" "$dest"
    echo "  copy  $src -> $dest"
  fi
}

print_profile_checklist() {
  local profile_guide="docs/your-profile.md"
  echo ""
  echo "  Profile checklist — edit config/profile.yaml before your first scrape."
  echo "  Full field guide: $profile_guide"
  echo ""
  echo "  Edit now:"
  echo "    • owner              — label in logs"
  echo "    • remote_preference  — fully_remote | hybrid_home_metro | any_us_remote"
  echo "    • home_metro         — name (display), zip_anchor, place_names (matching)"
  echo "    • silent_office_hubs — review defaults for misleading location columns"
  echo "    • comp               — min_ceiling_usd, min_floor_usd, gate2_floor_usd"
  echo "    • prescreen.stack_keywords — tools/skills for stack_hits"
  echo "    • tracks.enable      — start with [A] if unsure"
  echo ""
  echo "  Optional — set later:"
  echo "    • referrals.status_file      — warm/strong referral map"
  echo "    • verified_remote_employers  — after you confirm remote employers"
  echo "    • review_companies           — extra manual review tier"
  echo "    • paths.application_index    — already-applied HTML export"
}

open_doc() {
  local doc="$1"
  if [[ ! -f "$doc" ]]; then
    warn "Missing $doc"
    return
  fi
  if command -v open >/dev/null 2>&1; then
    open "$doc" || true
  else
    local ed="${EDITOR:-${VISUAL:-}}"
    if [[ -n "$ed" ]]; then
      # shellcheck disable=SC2086
      $ed "$doc" || true
    else
      echo "  Read: $REPO_ROOT/$doc"
    fi
  fi
}

open_profile_for_edit() {
  local profile="config/profile.yaml"
  local profile_guide="docs/your-profile.md"
  if [[ ! -f "$profile" ]]; then
    warn "Expected $profile after template copy — create it from config/profile.example.yaml"
    return
  fi
  print_profile_checklist
  if [[ ! -t 0 ]]; then
    echo "  Non-interactive: edit $profile and read $profile_guide before your first scrape."
    return
  fi
  read -r -p "Open $profile_guide now? [Y/n] " doc_ans
  doc_ans="${doc_ans:-Y}"
  if [[ "$doc_ans" =~ ^[Yy]$ ]]; then
    open_doc "$profile_guide"
  fi
  read -r -p "Open $profile in your editor now? [Y/n] " ans
  ans="${ans:-Y}"
  if [[ ! "$ans" =~ ^[Yy]$ ]]; then
    echo "  Remember to edit $profile before running the scraper."
    return
  fi
  local ed="${EDITOR:-${VISUAL:-}}"
  if [[ -n "$ed" ]]; then
    # shellcheck disable=SC2086
    $ed "$profile" || true
  elif command -v nano >/dev/null 2>&1; then
    nano "$profile" || true
  elif command -v vim >/dev/null 2>&1; then
    vim "$profile" || true
  else
    echo "  Set EDITOR or open manually: $REPO_ROOT/$profile"
  fi
}

step "QA-Job-Script onboarding"
echo "Repo: $REPO_ROOT"

step "1/5 — Python check"
if ! command -v python3 >/dev/null 2>&1; then
  warn "python3 not found. Install Python 3.10+ and re-run this script."
  exit 1
fi
PY_VER="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "  python3 version: $PY_VER"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  warn "Python 3.10+ recommended (found $PY_VER)."
fi

step "2/5 — Virtual environment (optional)"
if [[ -d ".venv" ]]; then
  echo "  .venv already exists"
elif [[ -t 0 ]]; then
  read -r -p "Create .venv here? [Y/n] " ans
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    python3 -m venv .venv
    echo "  created .venv"
  else
    echo "  skipped venv"
  fi
else
  echo "  non-interactive: skipping venv (run: python3 -m venv .venv)"
fi

PIP="python3 -m pip"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  PIP="pip"
  echo "  activated .venv"
fi

step "3/5 — Install dependencies"
$PIP install -r requirements.txt

step "4/5 — Copy config templates (only if missing)"
mkdir -p applications jobspy/results
copy_if_missing config/profile.example.yaml config/profile.yaml
copy_if_missing config/ils_matrix.example.yaml config/ils_matrix.yaml
copy_if_missing config/skip_companies.txt.example applications/skip_companies.txt
echo "  ILS (Interview Likelihood Score) is optional until you enable triage post-gates."
echo "  Matrix rubric and profile floors: docs/ils-matrix.md"

step "5/5 — Customize profile (required)"
open_profile_for_edit

echo ""
echo "  Profile field guide: docs/your-profile.md"
echo ""
echo "  Optional shell aliases:"
echo "    chmod +x scripts/install_alias.sh && ./scripts/install_alias.sh qa-job"
echo ""
echo "  Optional application index (already-applied companies): see docs/installation.md"
echo ""
echo "  Dry-run / verify install:"
echo "    QA_JOB_PROFILE=config/profile.test.yaml python3 -m pytest -q"
echo "    python3 scripts/triage_jobspy_csv.py --help"
echo "    python3 jobspy/run_search_locally.py   # first scrape (network; may take minutes)"
echo ""
echo "Done."

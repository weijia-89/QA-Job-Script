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
  echo "  Next: edit config/profile.yaml — your metro, pay floors, and skills."
  echo "  Walkthrough: $profile_guide"
  echo ""
  echo "  Must set before first scrape:"
  echo "    • owner              — any label for you (logs only)"
  echo "    • remote_preference  — how strict about remote vs hybrid"
  echo "    • home_metro         — your area cities and ZIP"
  echo "    • comp               — minimum pay you will consider"
  echo "    • prescreen.stack_keywords — tools to count in each posting"
  echo "    • tracks.enable      — [A] alone is fine to start"
  echo ""
  echo "  Can wait until later:"
  echo "    • referrals, verified_remote_employers, review_companies, application index"
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
  read -r -p "Open the profile walkthrough ($profile_guide) now? [Y/n] " doc_ans
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

step "Welcome — QA-Job-Script setup"
echo "This script prepares the job-search tool on your computer."
echo "Repo folder: $REPO_ROOT"

step "1/5 — Check for Python"
echo "  Python is the runtime that runs the scraper; we need version 3.10 or newer."
if ! command -v python3 >/dev/null 2>&1; then
  warn "python3 not found. Install Python 3.10+ (see docs/installation.md) and re-run."
  exit 1
fi
PY_VER="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "  Found python3 version: $PY_VER"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  warn "Python 3.10+ recommended (found $PY_VER)."
fi

step "2/5 — Optional isolated environment (.venv)"
echo "  A virtual environment keeps this project's packages separate from other apps."
if [[ -d ".venv" ]]; then
  echo "  .venv already exists — skipping create"
elif [[ -t 0 ]]; then
  read -r -p "Create .venv in this folder? [Y/n] " ans
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    python3 -m venv .venv
    echo "  Created .venv"
  else
    echo "  Skipped — you can create one later with: python3 -m venv .venv"
  fi
else
  echo "  Non-interactive: skipping venv (run: python3 -m venv .venv)"
fi

PIP="python3 -m pip"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  PIP="pip"
  echo "  Activated .venv for the rest of this script"
fi

step "3/5 — Install required packages"
echo "  Downloading libraries listed in requirements.txt (JobSpy, YAML, etc.)."
$PIP install -r requirements.txt

step "4/5 — Copy starter settings (only if missing)"
echo "  These are your personal config files — never overwritten if they already exist."
mkdir -p applications jobspy/results
copy_if_missing config/profile.example.yaml config/profile.yaml
copy_if_missing config/ils_matrix.example.yaml config/ils_matrix.yaml
copy_if_missing config/skip_companies.txt.example applications/skip_companies.txt

step "5/5 — Customize your profile"
echo "  profile.yaml tells the tool where you live, what pay to require, and which skills to look for."
open_profile_for_edit

echo ""
echo "────────────────────────────────────────"
echo "  Setup complete."
echo ""
echo "  Before your first job search:"
echo "    1. Finish editing config/profile.yaml (guide: docs/your-profile.md)"
echo "    2. Run: python3 jobspy/run_search_locally.py"
echo "    3. Then: python3 scripts/triage_jobspy_csv.py --latest --no-post-gates"
echo ""
echo "  Optional shortcuts: scripts/install_alias.sh qa-job"
echo "  More help: docs/installation.md"
echo ""
echo "  When you are ready to tune interview-likelihood scoring, read:"
echo "    docs/ils-matrix.md"
echo "  (You can ignore that file for your first few runs.)"
echo "────────────────────────────────────────"
echo ""
echo "Done."

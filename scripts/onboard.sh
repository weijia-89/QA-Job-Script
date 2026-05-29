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
copy_if_missing config/application_index.html.example applications/application_index.html

step "5/5 — Next steps"
echo "  Edit config/profile.yaml for your metro, comp floors, and stack keywords."
echo ""
echo "  Optional shell aliases:"
echo "    chmod +x scripts/install_alias.sh && ./scripts/install_alias.sh qa-job"
echo ""
echo "  Dry-run / verify install:"
echo "    QA_JOB_PROFILE=config/profile.test.yaml python3 -m pytest -q"
echo "    python3 scripts/triage_jobspy_csv.py --help"
echo "    python3 jobspy/run_search_locally.py   # first scrape (network; may take minutes)"
echo ""
echo "Done."

#!/usr/bin/env bash
# Install shell aliases for the QA-Job-Script pipeline (bash/zsh on macOS/Linux).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALIAS_NAME="${1:-qa-job}"
SHELL_RC="${2:-}"

detect_rc() {
  if [[ -n "$SHELL_RC" ]]; then
    echo "$SHELL_RC"
    return
  fi
  case "${SHELL:-}" in
    */zsh) echo "${ZDOTDIR:-$HOME}/.zshrc" ;;
    */bash) echo "$HOME/.bashrc" ;;
    *) echo "$HOME/.profile" ;;
  esac
}

RC_FILE="$(detect_rc)"
MARKER="# QA-Job-Script aliases"
BLOCK=$(cat <<EOF
${MARKER}
alias ${ALIAS_NAME}='cd "${REPO_ROOT}" && python3 jobspy/run_search_locally.py'
alias ${ALIAS_NAME}-triage='cd "${REPO_ROOT}" && python3 scripts/triage_jobspy_csv.py --latest --no-post-gates'
alias ${ALIAS_NAME}-triage-ils='cd "${REPO_ROOT}" && python3 scripts/triage_jobspy_csv.py --latest'
EOF
)

if [[ -f "$RC_FILE" ]] && grep -qF "$MARKER" "$RC_FILE"; then
  echo "Aliases already present in $RC_FILE (remove the QA-Job-Script block to reinstall)."
else
  {
    echo ""
    echo "$BLOCK"
  } >>"$RC_FILE"
  echo "Appended aliases to $RC_FILE"
fi

echo ""
echo "Reload your shell: source \"$RC_FILE\""
echo "Then run: ${ALIAS_NAME}"

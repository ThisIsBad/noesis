#!/usr/bin/env bash
# Boot Hegemonikon (port 8010) connected to the local 8-service stack.
# Linux/macOS/WSL equivalent of run-hegemonikon.ps1.
#
# Auth: Hegemonikon drives Claude via claude-agent-sdk, which spawns the
# `claude` CLI as a subprocess. The CLI uses the same credentials
# your Claude Code already does (Pro/Max OAuth in ~/.claude/, or
# ANTHROPIC_API_KEY env var, in that order). YOU DO NOT NEED AN
# API KEY if you're already logged into Claude Code.
#
# Sets all NOESIS_<SVC>_URL/SECRET pairs to the dev defaults
# scripts/run-stack.sh uses, plus HEGEMONIKON_SECRET=dev-hegemonikon-secret.
# Runs Hegemonikon in the foreground; Ctrl+C cleanly stops it.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# Make sure `claude` is on PATH so the SDK can spawn it. If not, hint
# at the install path before we crash mid-session with a cryptic error.
if ! command -v claude >/dev/null 2>&1; then
  echo
  echo "WARN: 'claude' CLI not found on PATH."
  echo "Hegemonikon drives Claude via the claude-agent-sdk, which spawns"
  echo "the 'claude' CLI as a subprocess. Install Claude Code first,"
  echo "then log in with your Pro/Max account:"
  echo "  https://docs.claude.com/en/docs/claude-code/quickstart"
  echo
  echo "If you'd prefer to authenticate via raw API key instead, set:"
  echo "  export ANTHROPIC_API_KEY='sk-ant-...'"
  echo
  read -rp "Continue anyway? (y/N) " ans
  case "$ans" in
    y|Y) ;;
    *) exit 1 ;;
  esac
fi

export PYTHONPATH="$REPO/schemas/src:$REPO/kairos/src:$REPO/clients/src:$REPO/ui/theoria/src:$REPO/services/hegemonikon/src"
export PORT=8010
export HEGEMONIKON_SECRET=dev-hegemonikon-secret
export HEGEMONIKON_MAX_BUDGET_USD=0.25

export NOESIS_LOGOS_URL=http://127.0.0.1:8001    NOESIS_LOGOS_SECRET=dev-logos-secret
export NOESIS_MNEME_URL=http://127.0.0.1:8002    NOESIS_MNEME_SECRET=dev-mneme-secret
export NOESIS_PRAXIS_URL=http://127.0.0.1:8003   NOESIS_PRAXIS_SECRET=dev-praxis-secret
export NOESIS_TELOS_URL=http://127.0.0.1:8004    NOESIS_TELOS_SECRET=dev-telos-secret
export NOESIS_EPISTEME_URL=http://127.0.0.1:8005 NOESIS_EPISTEME_SECRET=dev-episteme-secret
export NOESIS_KOSMOS_URL=http://127.0.0.1:8006   NOESIS_KOSMOS_SECRET=dev-kosmos-secret
export NOESIS_EMPIRIA_URL=http://127.0.0.1:8007  NOESIS_EMPIRIA_SECRET=dev-empiria-secret
export NOESIS_TECHNE_URL=http://127.0.0.1:8008   NOESIS_TECHNE_SECRET=dev-techne-secret

echo "Starting Hegemonikon on http://127.0.0.1:8010/"
echo "Open the page, paste 'dev-hegemonikon-secret' in the Bearer field,"
echo "then send a prompt. Ctrl+C here when done."
echo

exec python -m hegemonikon.mcp_server_http

#!/usr/bin/env bash
# Boot Console (port 8010) connected to the local 8-service stack.
# Linux/macOS/WSL equivalent of run-console.ps1.
#
# Reads ANTHROPIC_API_KEY from the current shell; prompts (silently)
# if unset. Sets all NOESIS_<SVC>_URL/SECRET pairs to the dev defaults
# scripts/run-stack.sh uses, plus CONSOLE_SECRET=dev-console-secret.
# Runs Console in the foreground; Ctrl+C cleanly stops it.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [ -z "${ANTHROPIC_API_KEY-}" ]; then
  read -rsp "ANTHROPIC_API_KEY (hidden): " ANTHROPIC_API_KEY
  echo
  export ANTHROPIC_API_KEY
fi

export PYTHONPATH="$REPO/schemas/src:$REPO/kairos/src:$REPO/clients/src:$REPO/ui/theoria/src:$REPO/services/console/src"
export PORT=8010
export CONSOLE_SECRET=dev-console-secret
export CONSOLE_MAX_BUDGET_USD=0.25

export NOESIS_LOGOS_URL=http://127.0.0.1:8001    NOESIS_LOGOS_SECRET=dev-logos-secret
export NOESIS_MNEME_URL=http://127.0.0.1:8002    NOESIS_MNEME_SECRET=dev-mneme-secret
export NOESIS_PRAXIS_URL=http://127.0.0.1:8003   NOESIS_PRAXIS_SECRET=dev-praxis-secret
export NOESIS_TELOS_URL=http://127.0.0.1:8004    NOESIS_TELOS_SECRET=dev-telos-secret
export NOESIS_EPISTEME_URL=http://127.0.0.1:8005 NOESIS_EPISTEME_SECRET=dev-episteme-secret
export NOESIS_KOSMOS_URL=http://127.0.0.1:8006   NOESIS_KOSMOS_SECRET=dev-kosmos-secret
export NOESIS_EMPIRIA_URL=http://127.0.0.1:8007  NOESIS_EMPIRIA_SECRET=dev-empiria-secret
export NOESIS_TECHNE_URL=http://127.0.0.1:8008   NOESIS_TECHNE_SECRET=dev-techne-secret

echo "Starting Console on http://127.0.0.1:8010/"
echo "Open the page, paste 'dev-console-secret' in the Bearer field,"
echo "then send a prompt. Ctrl+C here when done."
echo

exec python -m console.mcp_server_http

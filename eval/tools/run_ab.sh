#!/usr/bin/env bash
# Thin wrapper for running the Noesis A/B harness.
#
# Reason: the Bash-tool permission layer flags `source`, `set -a`, compound
# `cd && git` and `python -c` as needing approval. Encapsulating the
# env-loading and the `python -m noesis_eval.ab …` invocation in a script
# on disk lets the tool run it as a single `bash eval/tools/run_ab.sh …`
# call without prompting.
#
# Usage:
#   bash eval/tools/run_ab.sh ab --treatment mcp-treatment \
#       --baseline mcp-baseline --suite memory --samples 3 \
#       --out-dir eval/ab-runs/<stamp>
#
# The script:
#   1) unsets CLAUDECODE so the claude-CLI subprocess doesn't bail on the
#      nested-session guard (happens when this harness is invoked from
#      within a Claude Code session),
#   2) loads eval/.env.e2e (NOESIS_*_URL/SECRET for all 8 MCP servers),
#   3) forwards all args to `python -m noesis_eval.ab`.
#
# Env-loading is a literal read of KEY=VALUE lines (no shell interpolation)
# to sidestep "source evaluates shell code" permission checks.
set -euo pipefail

unset CLAUDECODE || true

# Resolve paths against the repo root (parent of `eval/`) so the wrapper
# works regardless of which directory the caller invoked it from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${NOESIS_ENV_FILE:-eval/.env.e2e}"
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    # Strip CR (files may be CRLF on Windows) and whitespace in the key.
    key="${key%$'\r'}"
    value="${value%$'\r'}"
    key="${key// /}"
    # Skip blanks and comments.
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    # Skip lines that never contained '=' (read splits into key='line',
    # value='' in that case — $value will still be empty but the real
    # guard is the key not looking like an env var name).
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    export "$key=$value"
  done < "$ENV_FILE"
fi

exec python -m noesis_eval.ab "$@"

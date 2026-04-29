#!/usr/bin/env bash
# End-to-end live-stack smoke test runnable in any Linux env (this
# Claude Code sandbox, GH Codespaces, Docker, …) without a browser
# and without an Anthropic key.
#
# Sequence:
#   1. boot the 8 services + Kairos      (scripts/run-stack.sh)
#   2. wait for /health on each          (scripts/probe-stack.sh)
#   3. boot Console with CONSOLE_FAKE_QUERY=1 in the background
#   4. drive Console with the canned prompt + validate the trace
#   5. tear everything down              (scripts/stop-stack.sh)
#
# Set CONSOLE_USE_REAL_CLAUDE=1 to skip the fake-query mode and drive
# Claude for real (requires logged-in `claude` CLI on PATH).
#
# Exit code: 0 if probe says ok, non-zero otherwise. Tear-down runs
# on every exit path.

set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN="$REPO/.run"
mkdir -p "$RUN/logs"

CONSOLE_PORT="${CONSOLE_PORT:-8010}"
CONSOLE_PIDFILE="$RUN/console.pid"

cleanup() {
  local code=$?
  echo
  echo "=== teardown ==="
  if [ -f "$CONSOLE_PIDFILE" ]; then
    local cpid
    cpid=$(cat "$CONSOLE_PIDFILE" 2>/dev/null || echo "")
    if [ -n "$cpid" ] && kill -0 "$cpid" 2>/dev/null; then
      kill "$cpid" 2>/dev/null || true
      sleep 1
      kill -9 "$cpid" 2>/dev/null || true
    fi
    rm -f "$CONSOLE_PIDFILE"
  fi
  bash "$REPO/scripts/stop-stack.sh" >/dev/null 2>&1 || true
  echo "  done."
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "=== 1/4: boot stack ==="
bash "$REPO/scripts/run-stack.sh"

echo
echo "=== 2/4: probe stack ==="
# probe-stack.sh polls /health on each service; we tolerate one retry.
if ! bash "$REPO/scripts/probe-stack.sh"; then
  echo "first probe failed — sleeping 3s and retrying once"
  sleep 3
  bash "$REPO/scripts/probe-stack.sh"
fi

echo
echo "=== 3/4: boot console ==="
fake_mode_env=()
if [ "${CONSOLE_USE_REAL_CLAUDE:-0}" != "1" ]; then
  fake_mode_env+=(CONSOLE_FAKE_QUERY=1)
  echo "  fake-query mode (set CONSOLE_USE_REAL_CLAUDE=1 to drive real Claude)"
else
  echo "  real-claude mode"
  if ! command -v claude >/dev/null 2>&1; then
    echo "  ERROR: claude CLI not on PATH — needed for real-Claude mode" >&2
    exit 3
  fi
fi

env "${fake_mode_env[@]}" \
    PYTHONPATH="$REPO/schemas/src:$REPO/kairos/src:$REPO/clients/src:$REPO/ui/theoria/src:$REPO/services/console/src" \
    PORT="$CONSOLE_PORT" \
    CONSOLE_SECRET=dev-console-secret \
    CONSOLE_MAX_BUDGET_USD=0.25 \
    NOESIS_LOGOS_URL=http://127.0.0.1:8001    NOESIS_LOGOS_SECRET=dev-logos-secret \
    NOESIS_MNEME_URL=http://127.0.0.1:8002    NOESIS_MNEME_SECRET=dev-mneme-secret \
    NOESIS_PRAXIS_URL=http://127.0.0.1:8003   NOESIS_PRAXIS_SECRET=dev-praxis-secret \
    NOESIS_TELOS_URL=http://127.0.0.1:8004    NOESIS_TELOS_SECRET=dev-telos-secret \
    NOESIS_EPISTEME_URL=http://127.0.0.1:8005 NOESIS_EPISTEME_SECRET=dev-episteme-secret \
    NOESIS_KOSMOS_URL=http://127.0.0.1:8006   NOESIS_KOSMOS_SECRET=dev-kosmos-secret \
    NOESIS_EMPIRIA_URL=http://127.0.0.1:8007  NOESIS_EMPIRIA_SECRET=dev-empiria-secret \
    NOESIS_TECHNE_URL=http://127.0.0.1:8008   NOESIS_TECHNE_SECRET=dev-techne-secret \
    python -m console.mcp_server_http \
    > "$RUN/logs/console.log" 2>&1 &
echo $! > "$CONSOLE_PIDFILE"
echo "  console -> :$CONSOLE_PORT  (pid $(cat "$CONSOLE_PIDFILE"))"

# Wait for /health.
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$CONSOLE_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$CONSOLE_PORT/health" >/dev/null 2>&1; then
  echo "  ERROR: console didn't become healthy on :$CONSOLE_PORT" >&2
  echo "  ---- last 40 lines of console.log ----"
  tail -40 "$RUN/logs/console.log" >&2 || true
  exit 4
fi
echo "  console healthy"

echo
echo "=== 4/4: drive e2e probe ==="
python "$REPO/tools/console_e2e_probe.py" \
  --base-url "http://127.0.0.1:$CONSOLE_PORT" \
  --bearer dev-console-secret

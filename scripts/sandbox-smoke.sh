#!/usr/bin/env bash
# End-to-end live-stack smoke test runnable in any Linux env (this
# Claude Code sandbox, GH Codespaces, Docker, …) without a browser
# and without an Anthropic key.
#
# Sequence:
#   1. boot the 8 services + Kairos      (scripts/run-stack.sh)
#   2. wait for /health on each          (scripts/probe-stack.sh)
#   3. boot Hegemonikon with HEGEMONIKON_FAKE_QUERY=1 in the background
#   4. drive Hegemonikon with the canned prompt + validate the trace
#   5. tear everything down              (scripts/stop-stack.sh)
#
# Set HEGEMONIKON_USE_REAL_CLAUDE=1 to skip the fake-query mode and drive
# Claude for real (requires logged-in `claude` CLI on PATH).
#
# Exit code: 0 if probe says ok, non-zero otherwise. Tear-down runs
# on every exit path.

set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN="$REPO/.run"
mkdir -p "$RUN/logs"

HEGEMONIKON_PORT="${HEGEMONIKON_PORT:-8010}"
HEGEMONIKON_PIDFILE="$RUN/hegemonikon.pid"

cleanup() {
  local code=$?
  echo
  echo "=== teardown ==="
  if [ -f "$HEGEMONIKON_PIDFILE" ]; then
    local cpid
    cpid=$(cat "$HEGEMONIKON_PIDFILE" 2>/dev/null || echo "")
    if [ -n "$cpid" ] && kill -0 "$cpid" 2>/dev/null; then
      kill "$cpid" 2>/dev/null || true
      sleep 1
      kill -9 "$cpid" 2>/dev/null || true
    fi
    rm -f "$HEGEMONIKON_PIDFILE"
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
echo "=== 3/4: boot hegemonikon ==="
fake_mode_env=()
if [ "${HEGEMONIKON_USE_REAL_CLAUDE:-0}" != "1" ]; then
  fake_mode_env+=(HEGEMONIKON_FAKE_QUERY=1)
  echo "  fake-query mode (set HEGEMONIKON_USE_REAL_CLAUDE=1 to drive real Claude)"
else
  echo "  real-claude mode"
  if ! command -v claude >/dev/null 2>&1; then
    echo "  ERROR: claude CLI not on PATH — needed for real-Claude mode" >&2
    exit 3
  fi
fi

env "${fake_mode_env[@]}" \
    PYTHONPATH="$REPO/schemas/src:$REPO/kairos/src:$REPO/clients/src:$REPO/ui/theoria/src:$REPO/services/hegemonikon/src" \
    PORT="$HEGEMONIKON_PORT" \
    HEGEMONIKON_SECRET=dev-hegemonikon-secret \
    HEGEMONIKON_MAX_BUDGET_USD=0.25 \
    NOESIS_LOGOS_URL=http://127.0.0.1:8001    NOESIS_LOGOS_SECRET=dev-logos-secret \
    NOESIS_MNEME_URL=http://127.0.0.1:8002    NOESIS_MNEME_SECRET=dev-mneme-secret \
    NOESIS_PRAXIS_URL=http://127.0.0.1:8003   NOESIS_PRAXIS_SECRET=dev-praxis-secret \
    NOESIS_TELOS_URL=http://127.0.0.1:8004    NOESIS_TELOS_SECRET=dev-telos-secret \
    NOESIS_EPISTEME_URL=http://127.0.0.1:8005 NOESIS_EPISTEME_SECRET=dev-episteme-secret \
    NOESIS_KOSMOS_URL=http://127.0.0.1:8006   NOESIS_KOSMOS_SECRET=dev-kosmos-secret \
    NOESIS_EMPIRIA_URL=http://127.0.0.1:8007  NOESIS_EMPIRIA_SECRET=dev-empiria-secret \
    NOESIS_TECHNE_URL=http://127.0.0.1:8008   NOESIS_TECHNE_SECRET=dev-techne-secret \
    python -m hegemonikon.mcp_server_http \
    > "$RUN/logs/hegemonikon.log" 2>&1 &
echo $! > "$HEGEMONIKON_PIDFILE"
echo "  hegemonikon -> :$HEGEMONIKON_PORT  (pid $(cat "$HEGEMONIKON_PIDFILE"))"

# Wait for /health.
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:$HEGEMONIKON_PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:$HEGEMONIKON_PORT/health" >/dev/null 2>&1; then
  echo "  ERROR: hegemonikon didn't become healthy on :$HEGEMONIKON_PORT" >&2
  echo "  ---- last 40 lines of hegemonikon.log ----"
  tail -40 "$RUN/logs/hegemonikon.log" >&2 || true
  exit 4
fi
echo "  hegemonikon healthy"

echo
echo "=== 4/4: drive e2e probe ==="
python "$REPO/tools/hegemonikon_e2e_probe.py" \
  --base-url "http://127.0.0.1:$HEGEMONIKON_PORT" \
  --bearer dev-hegemonikon-secret

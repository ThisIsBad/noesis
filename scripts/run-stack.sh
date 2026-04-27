#!/usr/bin/env bash
# Boot the eight Noesis MCP services + Kairos as plain Python processes
# on 127.0.0.1:8001-8009. Linux/macOS/WSL equivalent of run-stack.ps1.
#
# Logs to <repo>/.run/logs/<svc>.log; pid files to <repo>/.run/<svc>.pid.
# Stop with scripts/stop-stack.sh; probe with scripts/probe-stack.sh.

set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN="$REPO/.run"
mkdir -p "$RUN/logs" "$RUN/data/mneme" "$RUN/data/praxis" "$RUN/data/empiria" "$RUN/data/techne"

PYBASE="$REPO/schemas/src:$REPO/kairos/src:$REPO/clients/src"

start() {
  local name=$1 port=$2 srcdir=$3 module=$4
  shift 4
  local logfile="$RUN/logs/$name.log"
  PYTHONPATH="$srcdir:$PYBASE" \
    PORT="$port" \
    "$@" \
    python -m "$module" \
    > "$logfile" 2>&1 &
  echo $! > "$RUN/$name.pid"
  printf "  %-9s -> :%s (pid %s)\n" "$name" "$port" "$(cat "$RUN/$name.pid")"
}

start_kairos() {
  PYTHONPATH="$REPO/kairos/src:$REPO/schemas/src" \
    python -m uvicorn kairos.mcp_server_http:app \
      --host 127.0.0.1 --port 8009 \
      > "$RUN/logs/kairos.log" 2>&1 &
  echo $! > "$RUN/kairos.pid"
  printf "  %-9s -> :%s (pid %s)\n" "kairos" "8009" "$(cat "$RUN/kairos.pid")"
}

echo "Booting Noesis stack on 127.0.0.1:8001-8009 ..."

start_kairos
sleep 2

env LOGOS_SECRET=dev-logos-secret KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/logos/src:$PYBASE \
    PORT=8001 python -m logos.mcp_server_http \
    > $RUN/logs/logos.log 2>&1 & echo \$! > $RUN/logos.pid"
printf "  %-9s -> :%s (pid %s)\n" "logos" "8001" "$(cat "$RUN/logos.pid")"

env MNEME_SECRET=dev-mneme-secret MNEME_DATA_DIR="$RUN/data/mneme" \
    LOGOS_URL=http://127.0.0.1:8001 LOGOS_SECRET=dev-logos-secret \
    KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/mneme/src:$PYBASE \
    PORT=8002 python -m mneme.mcp_server_http \
    > $RUN/logs/mneme.log 2>&1 & echo \$! > $RUN/mneme.pid"
printf "  %-9s -> :%s (pid %s)\n" "mneme" "8002" "$(cat "$RUN/mneme.pid")"

env PRAXIS_SECRET=dev-praxis-secret PRAXIS_DATA_DIR="$RUN/data/praxis" \
    LOGOS_URL=http://127.0.0.1:8001 LOGOS_SECRET=dev-logos-secret \
    KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/praxis/src:$PYBASE \
    PORT=8003 python -m praxis.mcp_server_http \
    > $RUN/logs/praxis.log 2>&1 & echo \$! > $RUN/praxis.pid"
printf "  %-9s -> :%s (pid %s)\n" "praxis" "8003" "$(cat "$RUN/praxis.pid")"

env TELOS_SECRET=dev-telos-secret KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/telos/src:$PYBASE \
    PORT=8004 python -m telos.mcp_server_http \
    > $RUN/logs/telos.log 2>&1 & echo \$! > $RUN/telos.pid"
printf "  %-9s -> :%s (pid %s)\n" "telos" "8004" "$(cat "$RUN/telos.pid")"

env EPISTEME_SECRET=dev-episteme-secret KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/episteme/src:$PYBASE \
    PORT=8005 python -m episteme.mcp_server_http \
    > $RUN/logs/episteme.log 2>&1 & echo \$! > $RUN/episteme.pid"
printf "  %-9s -> :%s (pid %s)\n" "episteme" "8005" "$(cat "$RUN/episteme.pid")"

env KOSMOS_SECRET=dev-kosmos-secret KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/kosmos/src:$PYBASE \
    PORT=8006 python -m kosmos.mcp_server_http \
    > $RUN/logs/kosmos.log 2>&1 & echo \$! > $RUN/kosmos.pid"
printf "  %-9s -> :%s (pid %s)\n" "kosmos" "8006" "$(cat "$RUN/kosmos.pid")"

env EMPIRIA_SECRET=dev-empiria-secret EMPIRIA_DATA_DIR="$RUN/data/empiria" \
    KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/empiria/src:$PYBASE \
    PORT=8007 python -m empiria.mcp_server_http \
    > $RUN/logs/empiria.log 2>&1 & echo \$! > $RUN/empiria.pid"
printf "  %-9s -> :%s (pid %s)\n" "empiria" "8007" "$(cat "$RUN/empiria.pid")"

env TECHNE_SECRET=dev-techne-secret TECHNE_DATA_DIR="$RUN/data/techne" \
    KAIROS_URL=http://127.0.0.1:8009 \
  bash -c "PYTHONPATH=$REPO/services/techne/src:$PYBASE \
    PORT=8008 python -m techne.mcp_server_http \
    > $RUN/logs/techne.log 2>&1 & echo \$! > $RUN/techne.pid"
printf "  %-9s -> :%s (pid %s)\n" "techne" "8008" "$(cat "$RUN/techne.pid")"

echo ""
echo "All started. Logs in $RUN/logs; pid files in $RUN."
echo "Probe with:    bash scripts/probe-stack.sh"
echo "Stop with:     bash scripts/stop-stack.sh"

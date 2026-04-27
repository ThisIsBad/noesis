#!/usr/bin/env bash
# Stop the Noesis stack started by run-stack.sh. Idempotent.

set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUN="$REPO/.run"
[ -d "$RUN" ] || { echo "no $RUN; nothing to stop."; exit 0; }

for svc in console kairos logos mneme praxis telos episteme kosmos empiria techne; do
  pidfile="$RUN/$svc.pid"
  [ -f "$pidfile" ] || continue
  pid=$(cat "$pidfile")
  if kill "$pid" 2>/dev/null; then
    echo "  killed $svc (pid $pid)"
  else
    echo "  $svc (pid $pid) already gone"
  fi
  rm -f "$pidfile"
done

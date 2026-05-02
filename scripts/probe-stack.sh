#!/usr/bin/env bash
# Probe each Noesis service's /health (and Console at :8010 if up).
# Equivalent of tools/probe_live_stack.py for the local-bare-metal stack.

declare -A names=(
  [8001]=logos [8002]=mneme [8003]=praxis [8004]=telos
  [8005]=episteme [8006]=kosmos [8007]=empiria [8008]=techne
  [8009]=kairos [8010]=console
)
all_ok=true
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do
  status=$(curl -s -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$port/health" --max-time 3 || echo "000")
  if [ "$status" = "200" ]; then
    emoji="✓"
  else
    emoji="✗"
    all_ok=false
  fi
  printf "  %s :%-5s %-9s -> %s\n" "$emoji" "$port" "${names[$port]}" "$status"
done

$all_ok || exit 1

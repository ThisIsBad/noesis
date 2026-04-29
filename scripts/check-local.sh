#!/usr/bin/env bash
# Aggregated lint + typecheck + test gate. Mirrors what GH Actions would
# run for every component, but in this Linux sandbox in <60s.
#
# Iterates over the 14 packages, running ruff (check + format), mypy, and
# pytest+coverage. STATUS.md drift detection runs once at the end.
#
# Usage:
#   bash scripts/check-local.sh                 # full gate
#   bash scripts/check-local.sh --fast          # skip mypy + slow integration tests
#   bash scripts/check-local.sh --component foo # restrict to a single package label
#
# Exit code: number of failed stages (0 = green).

set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

FAST=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --fast) FAST=1; shift ;;
    --component) ONLY="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

failures=()
successes=()

run_stage() {
  local label=$1; shift
  echo "  · $label"
  if "$@" >/tmp/check-local.last 2>&1; then
    successes+=("$label")
  else
    failures+=("$label")
    echo "    FAIL — last 25 lines:"
    tail -25 /tmp/check-local.last | sed 's/^/      /'
  fi
}

check_component() {
  local label=$1 dir=$2
  if [ -n "$ONLY" ] && [ "$label" != "$ONLY" ]; then
    return
  fi
  echo
  echo "=== $label  ($dir) ==="
  pushd "$REPO/$dir" >/dev/null

  # Discover what to lint/test based on what exists.
  local src_paths=()
  [ -d src ] && src_paths+=(src)
  [ -d tests ] && src_paths+=(tests)
  if [ ${#src_paths[@]} -eq 0 ]; then
    echo "  · skipped — no src/ or tests/"
    popd >/dev/null
    return
  fi

  run_stage "$label  ruff check"      python -m ruff check "${src_paths[@]}"
  run_stage "$label  ruff format"     python -m ruff format --check "${src_paths[@]}"

  if [ "$FAST" -eq 0 ] && [ -d src ]; then
    run_stage "$label  mypy"          python -m mypy src
  fi

  if [ -d tests ]; then
    if [ "$FAST" -eq 1 ]; then
      run_stage "$label  pytest (fast)" python -m pytest -q -x --no-cov
    else
      run_stage "$label  pytest+cov"  python -m pytest -q
    fi
  fi

  popd >/dev/null
}

check_component "schemas"          "schemas"
check_component "kairos"           "kairos"
check_component "clients"          "clients"
check_component "logos"            "services/logos"
check_component "telos"            "services/telos"
check_component "praxis"           "services/praxis"
check_component "episteme"         "services/episteme"
check_component "kosmos"           "services/kosmos"
check_component "empiria"          "services/empiria"
check_component "mneme"            "services/mneme"
check_component "techne"           "services/techne"
check_component "console"          "services/console"
check_component "eval"             "eval"
check_component "theoria"          "ui/theoria"

# STATUS.md drift detection runs once, against the repo as a whole.
if [ -z "$ONLY" ]; then
  echo
  echo "=== STATUS.md drift ==="
  run_stage "STATUS.md current"     python "$REPO/tools/generate_status.py" --check
fi

echo
echo "================================================================"
echo "CHECK-LOCAL SUMMARY"
echo "================================================================"
echo "OK:   ${#successes[@]} stages"
if [ ${#failures[@]} -gt 0 ]; then
  echo "FAIL: ${#failures[@]} stages"
  for f in "${failures[@]}"; do echo "  - $f"; done
  exit "${#failures[@]}"
fi
echo "all green."

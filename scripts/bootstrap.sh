#!/usr/bin/env bash
# One-shot install of every Python dep Hegemonikon + the 8 services need to
# boot locally. Idempotent. Tolerates per-service install failures —
# reports them and keeps going. Most common breakage is chromadb / hnswlib
# (used by Mneme, Techne, Empiria); the rest of the stack runs fine without.

set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
failures=()
successes=()

try_install() {
  local label=$1 dir=$2 extras=${3:-}
  local target="."
  [ -n "$extras" ] && target=".[$extras]"

  echo
  echo "=== $label ==="
  pushd "$REPO/$dir" >/dev/null
  if python -m pip install -e "$target"; then
    successes+=("$label")
  else
    failures+=("$label  (pip exit $?)")
  fi
  popd >/dev/null
}

echo "=== upgrade pip ==="
python -m pip install --upgrade pip

try_install "schemas (shared contracts)"       "schemas"
try_install "kairos (tracing client)"          "kairos"
try_install "clients (bearer + persistence)"   "clients"

try_install "services/logos (Z3 verification)"   "services/logos"   "http"
try_install "services/telos (goal contracts)"    "services/telos"
try_install "services/praxis (planning)"         "services/praxis"
try_install "services/episteme (calibration)"    "services/episteme"
try_install "services/kosmos (causal model)"     "services/kosmos"
try_install "services/empiria (lessons)"         "services/empiria"
try_install "services/mneme (memory; chromadb)"  "services/mneme"
try_install "services/techne (skills; chromadb)" "services/techne"

try_install "services/hegemonikon (chat surface)"  "services/hegemonikon" "dev"
try_install "eval (A/B harness)"               "eval"

echo
echo "================================================================"
echo "BOOTSTRAP SUMMARY"
echo "================================================================"
echo "OK:   ${#successes[@]}"
for s in "${successes[@]}"; do echo "  + $s"; done

if [ ${#failures[@]} -gt 0 ]; then
  echo
  echo "FAIL: ${#failures[@]}"
  for f in "${failures[@]}"; do echo "  - $f"; done
  echo
  echo "Most likely cause: chromadb / hnswlib failed to build (needs C++"
  echo "build tools). Mneme + Techne + Empiria need it; everyone else"
  echo "doesn't. Cheapest fix: pip install chromadb --only-binary=:all:"
fi

echo
echo "Next steps:"
echo "  1. Boot the stack:    bash scripts/run-stack.sh"
echo "  2. Probe everything:  bash scripts/probe-stack.sh"
echo "  3. Boot Hegemonikon:      bash scripts/run-hegemonikon.sh"
echo "  4. Open browser:      http://127.0.0.1:8010/  (bearer = dev-hegemonikon-secret)"

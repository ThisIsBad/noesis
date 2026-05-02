<#
.SYNOPSIS
  One-shot install of every Python dep Console + the 8 services need
  to boot locally on Windows. Idempotent (safe to re-run).

.DESCRIPTION
  Walks the monorepo's pyprojects in dependency order — schemas first
  (everyone needs the contract types), then kairos + clients (every
  service uses tracing + bearer middleware), then each service, then
  Console.

  Tolerates per-service install failures: reports them at the end and
  keeps going. Most common breakage on Windows is ``chromadb`` /
  ``hnswlib`` failing to build; that affects Mneme, Techne, Empiria.
  The rest of the stack (Logos, Praxis, Telos, Episteme, Kosmos,
  Console) runs without ChromaDB. Console silently skips services
  whose URL is unreachable, so a partial-stack run is still useful
  for a smoke test.

.PARAMETER Repo
  Repository root. Defaults to the parent of the script's directory.

.EXAMPLE
  pwsh scripts/bootstrap-windows.ps1
  # When done, run:
  #   pwsh scripts/run-stack.ps1
  #   pwsh scripts/run-console.ps1
#>

param(
  [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Continue"   # we collect failures, don't abort
$failures = @()
$successes = @()

function Try-Install {
  param([string]$Label, [string]$Dir, [string]$Extras = "")
  Write-Host ""
  Write-Host "=== $Label ===" -ForegroundColor Cyan
  $target = if ($Extras) { ".[$Extras]" } else { "." }
  Push-Location (Join-Path $Repo $Dir)
  try {
    python -m pip install -e $target 2>&1 | Tee-Object -Variable output
    if ($LASTEXITCODE -eq 0) {
      $script:successes += $Label
    } else {
      $script:failures += "$Label  (pip exit $LASTEXITCODE)"
    }
  } catch {
    $script:failures += "$Label  ($_)"
  } finally {
    Pop-Location
  }
}

# ── upgrade pip first; old pip can't resolve Python 3.11 wheels ────────────
Write-Host "=== upgrade pip ===" -ForegroundColor Cyan
python -m pip install --upgrade pip

# ── shared contracts (every component needs these) ─────────────────────────
Try-Install "schemas (shared contracts)"       "schemas"
Try-Install "kairos (tracing client)"          "kairos"
Try-Install "clients (bearer + persistence)"   "clients"

# ── services (each one is independent; failures don't block the rest) ──────
Try-Install "services/logos (Z3 verification)"     "services/logos" "http"
Try-Install "services/telos (goal contracts)"      "services/telos"
Try-Install "services/praxis (planning)"           "services/praxis"
Try-Install "services/episteme (calibration)"      "services/episteme"
Try-Install "services/kosmos (causal model)"       "services/kosmos"
Try-Install "services/empiria (lessons)"           "services/empiria"
Try-Install "services/mneme (memory; chromadb)"    "services/mneme"
Try-Install "services/techne (skills; chromadb)"   "services/techne"

# ── Console + the eval harness (gives you the in-process E2E suite too) ────
Try-Install "services/console (chat surface)"  "services/console" "dev"
Try-Install "eval (A/B harness)"               "eval"

Write-Host ""
Write-Host "================================================================" -ForegroundColor White
Write-Host "BOOTSTRAP SUMMARY" -ForegroundColor White
Write-Host "================================================================" -ForegroundColor White
Write-Host ("OK:   {0}" -f $successes.Count) -ForegroundColor Green
foreach ($s in $successes) { Write-Host "  + $s" -ForegroundColor Green }

if ($failures.Count -gt 0) {
  Write-Host ""
  Write-Host ("FAIL: {0}" -f $failures.Count) -ForegroundColor Yellow
  foreach ($f in $failures) { Write-Host "  - $f" -ForegroundColor Yellow }
  Write-Host ""
  Write-Host "Most likely cause on Windows:" -ForegroundColor Yellow
  Write-Host "  chromadb / hnswlib failed to build (needs C++ build tools)." -ForegroundColor Yellow
  Write-Host "  Mneme + Techne + Empiria need it; everyone else doesn't." -ForegroundColor Yellow
  Write-Host "  Cheapest fix: pip install chromadb --only-binary=:all:" -ForegroundColor Yellow
  Write-Host "  Or skip those three services for the smoke test — Console" -ForegroundColor Yellow
  Write-Host "  silently drops services whose URL is unreachable." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Boot the stack:    pwsh scripts/run-stack.ps1"
Write-Host "  2. Probe everything:  pwsh scripts/probe-stack.ps1"
Write-Host "  3. Boot Console:      pwsh scripts/run-console.ps1"
Write-Host "  4. Open browser:      http://127.0.0.1:8010/"
Write-Host "                        bearer = dev-console-secret"

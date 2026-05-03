<#
.SYNOPSIS
  Boot Hegemonikon (port 8010) connected to the local 8-service stack.

.DESCRIPTION
  Hegemonikon drives Claude via ``claude-agent-sdk``, which spawns the
  ``claude`` CLI as a subprocess. The CLI authenticates via the same
  credentials your Claude Code uses (Pro / Max OAuth in ``~/.claude/``,
  or a raw ANTHROPIC_API_KEY env var, in that order). **You do NOT
  need an API key if you're already logged into Claude Code.**

  Sets all NOESIS_<SVC>_URL + NOESIS_<SVC>_SECRET pairs to the dev
  defaults that scripts/run-stack.ps1 uses, plus
  HEGEMONIKON_SECRET=dev-hegemonikon-secret. Runs Hegemonikon in the FOREGROUND
  (Ctrl+C cleanly stops it).

.EXAMPLE
  pwsh scripts/run-hegemonikon.ps1
  # then open http://127.0.0.1:8010/  ->  bearer = dev-hegemonikon-secret

.EXAMPLE
  # Override with a raw API key if you don't want to use your CLI session:
  $env:ANTHROPIC_API_KEY = 'sk-ant-...'
  pwsh scripts/run-hegemonikon.ps1
#>

param(
  [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"

# Sanity-check: make sure `claude` is on PATH so the SDK can spawn it.
# If it's not, point at the official install instructions instead of
# letting the user hit a cryptic SDK error mid-session.
$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudeCmd) {
  Write-Host ""
  Write-Warning "``claude`` CLI not found on PATH."
  Write-Host  "Hegemonikon drives Claude via the claude-agent-sdk, which spawns the"
  Write-Host  "``claude`` CLI as a subprocess. Install Claude Code first, then"
  Write-Host  "log in with your Pro/Max account:"
  Write-Host  "  https://docs.claude.com/en/docs/claude-code/quickstart"
  Write-Host  ""
  Write-Host  "If you'd prefer to authenticate via raw API key instead, set:"
  Write-Host  "  `$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
  Write-Host  ""
  $continue = Read-Host "Continue anyway? (y/N)"
  if ($continue -notmatch '^[yY]') { exit 1 }
}

$Sep = [IO.Path]::PathSeparator
$env:PYTHONPATH = @(
  Join-Path $Repo 'schemas/src'
  Join-Path $Repo 'kairos/src'
  Join-Path $Repo 'clients/src'
  Join-Path $Repo 'ui/theoria/src'
  Join-Path $Repo 'services/hegemonikon/src'
) -join $Sep

$env:PORT                    = '8010'
$env:HEGEMONIKON_SECRET          = 'dev-hegemonikon-secret'
$env:HEGEMONIKON_MAX_BUDGET_USD  = '0.25'

$env:NOESIS_LOGOS_URL        = 'http://127.0.0.1:8001'
$env:NOESIS_LOGOS_SECRET     = 'dev-logos-secret'
$env:NOESIS_MNEME_URL        = 'http://127.0.0.1:8002'
$env:NOESIS_MNEME_SECRET     = 'dev-mneme-secret'
$env:NOESIS_PRAXIS_URL       = 'http://127.0.0.1:8003'
$env:NOESIS_PRAXIS_SECRET    = 'dev-praxis-secret'
$env:NOESIS_TELOS_URL        = 'http://127.0.0.1:8004'
$env:NOESIS_TELOS_SECRET     = 'dev-telos-secret'
$env:NOESIS_EPISTEME_URL     = 'http://127.0.0.1:8005'
$env:NOESIS_EPISTEME_SECRET  = 'dev-episteme-secret'
$env:NOESIS_KOSMOS_URL       = 'http://127.0.0.1:8006'
$env:NOESIS_KOSMOS_SECRET    = 'dev-kosmos-secret'
$env:NOESIS_EMPIRIA_URL      = 'http://127.0.0.1:8007'
$env:NOESIS_EMPIRIA_SECRET   = 'dev-empiria-secret'
$env:NOESIS_TECHNE_URL       = 'http://127.0.0.1:8008'
$env:NOESIS_TECHNE_SECRET    = 'dev-techne-secret'

Write-Host "Starting Hegemonikon on http://127.0.0.1:8010/"
Write-Host "Open the page, paste 'dev-hegemonikon-secret' in the Bearer field,"
Write-Host "then send a prompt. Ctrl+C here when done."
Write-Host ""

python -m hegemonikon.mcp_server_http

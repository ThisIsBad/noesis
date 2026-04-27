<#
.SYNOPSIS
  Boot Console (port 8010) connected to the local 8-service stack.

.DESCRIPTION
  Reads ANTHROPIC_API_KEY from the current PowerShell environment;
  prompts if unset (input is hidden). Sets all NOESIS_<SVC>_URL +
  NOESIS_<SVC>_SECRET pairs to the dev defaults that scripts/run-stack.ps1
  uses, plus CONSOLE_SECRET=dev-console-secret.

  Runs Console in the FOREGROUND (so Ctrl+C cleanly stops it) — the
  other 8 services run in the background from run-stack.ps1.

.EXAMPLE
  $env:ANTHROPIC_API_KEY = 'sk-ant-...'
  pwsh scripts/run-console.ps1
  # then open http://127.0.0.1:8010/  →  bearer = dev-console-secret
#>

param(
  [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"

if (-not $env:ANTHROPIC_API_KEY) {
  $secure = Read-Host "ANTHROPIC_API_KEY (hidden)" -AsSecureString
  $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $env:ANTHROPIC_API_KEY = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
  [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$Sep = [IO.Path]::PathSeparator
$env:PYTHONPATH = @(
  Join-Path $Repo 'schemas/src'
  Join-Path $Repo 'kairos/src'
  Join-Path $Repo 'clients/src'
  Join-Path $Repo 'ui/theoria/src'
  Join-Path $Repo 'services/console/src'
) -join $Sep

$env:PORT                    = '8010'
$env:CONSOLE_SECRET          = 'dev-console-secret'
$env:CONSOLE_MAX_BUDGET_USD  = '0.25'

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

Write-Host "Starting Console on http://127.0.0.1:8010/"
Write-Host "Open the page, paste 'dev-console-secret' in the Bearer field,"
Write-Host "then send a prompt. Ctrl+C here when done."
Write-Host ""

python -m console.mcp_server_http

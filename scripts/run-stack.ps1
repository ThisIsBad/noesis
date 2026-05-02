<#
.SYNOPSIS
  Boot the eight Noesis MCP services + Kairos as background Python
  processes on 127.0.0.1:8001-8009. Windows-native equivalent of
  scripts/run-stack.sh.

.DESCRIPTION
  No Docker, no WSL, no compose. Each service is a `python -m
  <svc>.mcp_server_http` subprocess with the right PYTHONPATH and
  per-service env vars (data dir, dev secret, sidecar URLs).
  Logs go to <repo>/.run/logs/<svc>.log; pid files to
  <repo>/.run/<svc>.pid so scripts/stop-stack.ps1 can find them.

  Services that fail to boot (e.g. chromadb deps missing on Windows)
  are reported but don't block the others. Run
  `scripts/probe-stack.ps1` afterwards to see who's healthy.

.PARAMETER Repo
  Repository root. Defaults to the parent of the script's directory.

.EXAMPLE
  pwsh scripts/run-stack.ps1
  # Tail a specific service:
  Get-Content .run/logs/logos.log -Wait
  # Stop everything:
  pwsh scripts/stop-stack.ps1
#>

param(
  [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
$RunDir = Join-Path $Repo ".run"
$LogDir = Join-Path $RunDir "logs"
$DataDir = Join-Path $RunDir "data"
New-Item -ItemType Directory -Force -Path $RunDir, $LogDir, $DataDir | Out-Null
foreach ($s in 'mneme','praxis','techne','empiria') {
  New-Item -ItemType Directory -Force -Path (Join-Path $DataDir $s) | Out-Null
}

# Shared PYTHONPATH stem (semicolon-separated on Windows).
$Sep = [IO.Path]::PathSeparator
$PyBase = @(
  Join-Path $Repo 'schemas/src'
  Join-Path $Repo 'kairos/src'
  Join-Path $Repo 'clients/src'
) -join $Sep

function Start-Service {
  param(
    [string]$Name,
    [int]$Port,
    [string]$ServicePath,   # e.g. "services/logos/src" or "" for kairos uvicorn
    [string]$Module,        # e.g. "logos.mcp_server_http" or "uvicorn"
    [string[]]$ExtraArgs = @(),
    [hashtable]$EnvVars = @{}
  )

  $LogPath = Join-Path $LogDir "$Name.log"
  $PidPath = Join-Path $RunDir "$Name.pid"

  $PyPath = if ($ServicePath) { (Join-Path $Repo $ServicePath) + $Sep + $PyBase } else { $PyBase }
  $env:PYTHONPATH = $PyPath
  $env:PORT = "$Port"
  foreach ($k in $EnvVars.Keys) { Set-Item "Env:$k" $EnvVars[$k] }

  $argsList = @('-m', $Module) + $ExtraArgs
  $proc = Start-Process -FilePath "python" `
    -ArgumentList $argsList `
    -RedirectStandardOutput $LogPath `
    -RedirectStandardError "$LogPath.err" `
    -PassThru -WindowStyle Hidden -NoNewWindow:$false
  Set-Content -Path $PidPath -Value $proc.Id
  Write-Host ("  {0,-9} -> :{1} (pid {2})" -f $Name, $Port, $proc.Id)

  # Reset the env vars we set so they don't bleed into the next service.
  foreach ($k in $EnvVars.Keys) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
  Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  Remove-Item Env:PORT       -ErrorAction SilentlyContinue
}

Write-Host "Booting Noesis stack on 127.0.0.1:8001-8009 ..."

Start-Service -Name 'kairos' -Port 8009 -ServicePath '' -Module 'uvicorn' `
  -ExtraArgs @('kairos.mcp_server_http:app','--host','127.0.0.1','--port','8009')

Start-Sleep -Seconds 2

Start-Service -Name 'logos' -Port 8001 -ServicePath 'services/logos/src' `
  -Module 'logos.mcp_server_http' `
  -EnvVars @{
    LOGOS_SECRET = 'dev-logos-secret'
    KAIROS_URL   = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'mneme' -Port 8002 -ServicePath 'services/mneme/src' `
  -Module 'mneme.mcp_server_http' `
  -EnvVars @{
    MNEME_SECRET   = 'dev-mneme-secret'
    MNEME_DATA_DIR = (Join-Path $DataDir 'mneme')
    LOGOS_URL      = 'http://127.0.0.1:8001'
    LOGOS_SECRET   = 'dev-logos-secret'
    KAIROS_URL     = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'praxis' -Port 8003 -ServicePath 'services/praxis/src' `
  -Module 'praxis.mcp_server_http' `
  -EnvVars @{
    PRAXIS_SECRET   = 'dev-praxis-secret'
    PRAXIS_DATA_DIR = (Join-Path $DataDir 'praxis')
    LOGOS_URL       = 'http://127.0.0.1:8001'
    LOGOS_SECRET    = 'dev-logos-secret'
    KAIROS_URL      = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'telos' -Port 8004 -ServicePath 'services/telos/src' `
  -Module 'telos.mcp_server_http' `
  -EnvVars @{
    TELOS_SECRET = 'dev-telos-secret'
    KAIROS_URL   = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'episteme' -Port 8005 -ServicePath 'services/episteme/src' `
  -Module 'episteme.mcp_server_http' `
  -EnvVars @{
    EPISTEME_SECRET = 'dev-episteme-secret'
    KAIROS_URL      = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'kosmos' -Port 8006 -ServicePath 'services/kosmos/src' `
  -Module 'kosmos.mcp_server_http' `
  -EnvVars @{
    KOSMOS_SECRET = 'dev-kosmos-secret'
    KAIROS_URL    = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'empiria' -Port 8007 -ServicePath 'services/empiria/src' `
  -Module 'empiria.mcp_server_http' `
  -EnvVars @{
    EMPIRIA_SECRET   = 'dev-empiria-secret'
    EMPIRIA_DATA_DIR = (Join-Path $DataDir 'empiria')
    KAIROS_URL       = 'http://127.0.0.1:8009'
  }

Start-Service -Name 'techne' -Port 8008 -ServicePath 'services/techne/src' `
  -Module 'techne.mcp_server_http' `
  -EnvVars @{
    TECHNE_SECRET   = 'dev-techne-secret'
    TECHNE_DATA_DIR = (Join-Path $DataDir 'techne')
    KAIROS_URL      = 'http://127.0.0.1:8009'
  }

Write-Host ""
Write-Host "All started. Logs in $LogDir; pid files in $RunDir."
Write-Host "Probe with:    pwsh scripts/probe-stack.ps1"
Write-Host "Stop with:     pwsh scripts/stop-stack.ps1"

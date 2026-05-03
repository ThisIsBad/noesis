<#
.SYNOPSIS
  Stop the Noesis stack started by run-stack.ps1 (and run-hegemonikon.ps1
  if it's been backgrounded).

.DESCRIPTION
  Reads .run/<svc>.pid for each known service, kills the process,
  removes the pid file. Idempotent: missing pid files are skipped.
#>

param(
  [string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$RunDir = Join-Path $Repo ".run"
if (-not (Test-Path $RunDir)) {
  Write-Host "no $RunDir; nothing to stop."
  exit 0
}

$names = @('hegemonikon','kairos','logos','mneme','praxis','telos','episteme','kosmos','empiria','techne')
foreach ($name in $names) {
  $PidPath = Join-Path $RunDir "$name.pid"
  if (-not (Test-Path $PidPath)) { continue }
  $proc_id = (Get-Content $PidPath -Raw).Trim()
  try {
    Stop-Process -Id $proc_id -Force -ErrorAction Stop
    Write-Host ("  killed {0} (pid {1})" -f $name, $proc_id)
  } catch {
    Write-Host ("  {0} (pid {1}) already gone" -f $name, $proc_id)
  }
  Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
}

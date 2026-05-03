<#
.SYNOPSIS
  Probe each Noesis service's /health (and Hegemonikon too if running).
  Windows-native equivalent of `tools/probe_live_stack.py`.
#>

param(
  [int[]]$Ports = @(8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8010)
)

$names = @{
  8001 = 'logos'; 8002 = 'mneme'; 8003 = 'praxis'; 8004 = 'telos'
  8005 = 'episteme'; 8006 = 'kosmos'; 8007 = 'empiria'; 8008 = 'techne'
  8009 = 'kairos'; 8010 = 'hegemonikon'
}

$all_ok = $true
foreach ($port in $Ports) {
  $name = $names[$port]
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" `
      -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $status = $r.StatusCode
  } catch {
    $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode } else { 'down' }
  }
  $emoji = if ($status -eq 200) { 'OK ' } else { 'X  '; $all_ok = $false }
  Write-Host ("  {0} :{1} {2,-9} -> {3}" -f $emoji, $port, $name, $status)
}

if (-not $all_ok) { exit 1 }

# analyse-watch.ps1 -- task-18: correlate the window-watch log with the watchdog duty cycle.
# Pure ASCII, BOM.  Reports, for a given start time:
#   * new VISIBLE windows and how many are console-class,
#   * how many new console windows fall within +/-6 s of a logged watchdog run,
#   * the watchdog's own session id from its log.
param(
  [string]$WatchLog = (Join-Path $PSScriptRoot 'window-watch.log'),
  [string]$DutyLog = (Join-Path (Split-Path -Parent $PSScriptRoot) 'watchdog.log'),
  [string]$From = '01:59:18'
)
$ErrorActionPreference = 'Continue'
function ToSec([string]$hhmmss) { $p = $hhmmss.Split(':'); return ([int]$p[0]) * 3600 + ([int]$p[1]) * 60 + [int]$p[2] }

$fromSec = ToSec $From
$runs = New-Object System.Collections.ArrayList
foreach ($line in Get-Content -LiteralPath $DutyLog) {
  if ($line -match '^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (.*)$') {
    [void]$runs.Add([pscustomobject]@{ time = $Matches[2]; text = $Matches[3] })
  }
}
$runSecs = @($runs | Where-Object { (ToSec $_.time) -ge ($fromSec - 60) } | ForEach-Object { ToSec $_.time })

$newAll = New-Object System.Collections.ArrayList
$newConsole = New-Object System.Collections.ArrayList
$nearRunConsole = New-Object System.Collections.ArrayList
foreach ($line in Get-Content -LiteralPath $WatchLog) {
  if ($line -notmatch '^NEW (\d{2}:\d{2}:\d{2})\.\d+ console=(True|False) class=(\S+) sid=(\d+) pid=(\d+) proc=(\S*) title=(.*)$') { continue }
  $t = $Matches[1]; $isConsole = $Matches[2] -eq 'True'
  if ((ToSec $t) -lt $fromSec) { continue }
  $row = [pscustomobject]@{ time = $t; console = $isConsole; class = $Matches[3]; sid = [int]$Matches[4]; pid = [int]$Matches[5]; proc = $Matches[6]; title = $Matches[7] }
  [void]$newAll.Add($row)
  if ($isConsole) {
    [void]$newConsole.Add($row)
    foreach ($rs in $runSecs) {
      if ([math]::Abs((ToSec $t) - $rs) -le 6) { [void]$nearRunConsole.Add($row); break }
    }
  }
}

Write-Output ('analysis window: from ' + $From + '  (' + $newAll.Count + ' new visible windows)')
Write-Output ('  console-class among them      : ' + $newConsole.Count)
foreach ($r in $newConsole) { Write-Output ('    CONSOLE ' + $r.time + ' class=' + $r.class + ' sid=' + $r.sid + ' pid=' + $r.pid + ' proc=' + $r.proc) }
Write-Output ('  within +/-6 s of a watchdog run: ' + $nearRunConsole.Count)
foreach ($r in $nearRunConsole) { Write-Output ('    NEAR-RUN CONSOLE ' + $r.time + ' class=' + $r.class + ' sid=' + $r.sid) }
Write-Output ('  watchdog runs inside the window (from its log): ' + $runSecs.Count)
foreach ($rs in $runSecs) { $n = [int]$rs; Write-Output ('    run at ' + ('{0:d2}:{1:d2}:{2:d2}' -f [int]($n / 3600), [int](($n % 3600) / 60), ($n % 60))) }
$sess = @()
foreach ($line in Get-Content -LiteralPath $DutyLog) { if ($line -match 'session=(\d+)') { $sess += $Matches[1] } }
Write-Output ('  watchdog session ids seen in its log: ' + (($sess | Select-Object -Unique) -join ', '))
Write-Output ('  verdict: ' + $(if ($newConsole.Count -eq 0) { 'PASS - zero new console-class windows, zero near watchdog runs' } else { 'see the console lines above' }))

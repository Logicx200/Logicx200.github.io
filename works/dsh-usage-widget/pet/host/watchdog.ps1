# watchdog.ps1 -- silent self-healing for the DSH usage widget (task-17).
#
# The 2026-10-06 outage: the widget died once (assembly/policy failure) and NOTHING
# brought it back for a week, because the previous "heal every minute" task has been
# removed.  This one runs from the Task Scheduler every 4 minutes, checks whether the
# panel is alive, starts it ONLY when it is not, and then exits immediately - so a healthy
# period produces a clean result code (0) instead of the old 0x41370420 "task is already
# running" error every single minute.
#
# It never touches the DSH process, never writes anywhere except its own log, and is
# idempotent: the widget itself holds a single-instance mutex, so even two watchdogs
# racing cannot create two panels.
param(
  # Task that owns the real launcher (kept in one place: the widget task itself).
  [string]$TaskName = 'DshUsageWidget',
  [switch]$Quiet
)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here 'watchdog.log'
$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
# task-18: report our own session id. With the S4U (non-interactive) principal this must
# be 0 - session 0 has no desktop, so this task can never flash a console window.
$runSession = try { [System.Diagnostics.Process]::GetCurrentProcess().SessionId } catch { -1 }
$runUser = try { [System.Security.Principal.WindowsIdentity]::GetCurrent().Name } catch { '' }

function Note([string]$m) {
  try {
    Add-Content -LiteralPath $log -Value ($stamp + ' ' + $m) -Encoding UTF8
    # keep the log small: one line per action, trim to the last 200 lines
    $lines = @(Get-Content -LiteralPath $log -ErrorAction SilentlyContinue)
    if ($lines.Count -gt 200) { $lines | Select-Object -Last 200 | Set-Content -LiteralPath $log -Encoding UTF8 }
  } catch { }
  if (-not $Quiet) { Write-Host $m }
}

# 1. is the panel alive?  Two independent signals, either one is enough:
#    * a top-level window titled "DSH usage" (the panel's title, set in ui\widget.ps1)
#    * a powershell process whose command line runs ui\widget.ps1
$alive = $false
try {
  $procs = @(Get-Process -Name powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq 'DSH usage' })
  if ($procs.Count -gt 0) { $alive = $true }
} catch { }
if (-not $alive) {
  try {
    $mine = @()
    $cur = $PID
    while ($true) { $p = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue; if (-not $p) { break }; $cur = [int]$p.ParentProcessId; if ($cur -le 0) { break }; $mine += $cur }
    $hit = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object {
      $mine -notcontains $_.ProcessId -and $_.CommandLine -match 'ui\\widget\.ps1'
    }
    if (@($hit).Count -gt 0) { $alive = $true }
  } catch { }
}

if ($alive) {
  Note ('healthy: panel is running, nothing to do [session=' + $runSession + ' user=' + $runUser + ']')
  exit 0
}

# 2. not alive -> ask the widget's own task to start it (same entry point as logon)
Note ('panel NOT running -> starting task ' + $TaskName + ' [session=' + $runSession + ' user=' + $runUser + ']')
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Note ('start request accepted for ' + $TaskName)
} catch {
  Note ('start FAILED: ' + $_.Exception.Message)
}
exit 0

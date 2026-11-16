# window-watch.ps1 -- task-18 evidence instrument (fast, incremental).
#
# Samples VISIBLE top-level windows and logs every window that appears for the first time,
# together with the duty cycle of the two scheduled tasks (written incrementally so the log
# can be read live).  Purpose: prove the flashing console belongs to
# DshUsageWidgetWatchdog before the fix, then prove zero new console-class windows after it.
#
# Speed matters: a console that lives for ~1 s must not slip between samples.  The window
# scan therefore does NO per-window process lookup (the class + pid are enough); process
# names are resolved lazily only for the windows that are actually new.
param(
  [string]$Out = (Join-Path $PSScriptRoot 'window-watch.log'),
  [int]$Seconds = 900,
  [int]$IntervalMs = 400,
  [int]$DutyEveryMs = 3000
)
$ErrorActionPreference = 'Continue'
Add-Type -Namespace WW19 -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("kernel32.dll")] public static extern bool ProcessIdToSessionId(uint pid, out uint sid);
public delegate bool EnumProc(IntPtr h, IntPtr p);
'@ -ErrorAction SilentlyContinue

$script:seen = @{}
$script:newCount = 0
$script:newConsoleCount = 0
$script:samples = 0

function Get-VisibleWindows {
  $list = New-Object System.Collections.ArrayList
  $cb = [WW19.U+EnumProc]{
    param($h, $p)
    if ([WW19.U]::IsWindowVisible($h)) {
      $t = New-Object System.Text.StringBuilder 256
      [void][WW19.U]::GetWindowText($h, $t, 256)
      $c = New-Object System.Text.StringBuilder 256
      [void][WW19.U]::GetClassName($h, $c, 256)
      $wpid = [uint32]0
      [void][WW19.U]::GetWindowThreadProcessId($h, [ref]$wpid)
      [void]$list.Add([pscustomobject]@{ hwnd = [int64]$h; title = $t.ToString(); cls = $c.ToString(); pid = [int]$wpid })
    }
    return $true
  }
  [void][WW19.U]::EnumWindows($cb, [IntPtr]::Zero)
  return $list
}

function Duty([string]$tag) {
  $ts = (Get-Date).ToString('HH:mm:ss.fff')
  $parts = @()
  foreach ($tn in 'DshUsageWidget', 'DshUsageWidgetWatchdog') {
    try {
      $i = Get-ScheduledTaskInfo -TaskName $tn -ErrorAction SilentlyContinue
      $parts += ('{0}:last={1},res=0x{2:X},state={3}' -f $tn, $i.LastRunTime.ToString('HH:mm:ss'), $i.LastTaskResult,
                 (Get-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue).State)
    } catch { $parts += ($tn + ':n/a') }
  }
  ('DUTY {0} {1} | seen={2} new={3} newConsole={4} samples={5}' -f $ts, ($parts -join ' ; '), $script:seen.Count, $script:newCount, $script:newConsoleCount, $script:samples) |
    Add-Content -LiteralPath $Out -Encoding UTF8
}

"# window-watch start {0}  interval={1}ms  seconds={2}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $IntervalMs, $Seconds | Set-Content -LiteralPath $Out -Encoding UTF8
foreach ($w in Get-VisibleWindows) { $script:seen[[int64]$w.hwnd] = $true }
"# seeded {0} pre-existing visible window(s)" -f $script:seen.Count | Add-Content -LiteralPath $Out -Encoding UTF8
Duty 'seed'

$deadline = (Get-Date).AddSeconds($Seconds)
$nextDuty = (Get-Date)
while ((Get-Date) -lt $deadline) {
  $script:samples++
  foreach ($w in Get-VisibleWindows) {
    if (-not $script:seen.ContainsKey([int64]$w.hwnd)) {
      $script:seen[[int64]$w.hwnd] = $true
      $script:newCount++
      $isConsole = ($w.cls -match 'Console|CASCADIA|PseudoConsole|Terminal')
      if ($isConsole) { $script:newConsoleCount++ }
      $sid = [uint32]0
      [void][WW19.U]::ProcessIdToSessionId([uint32]$w.pid, [ref]$sid)
      $proc = ''
      try { $proc = (Get-Process -Id $w.pid -ErrorAction SilentlyContinue).ProcessName } catch { }
      "NEW {0} console={1} class={2} sid={3} pid={4} proc={5} title={6}" -f (Get-Date).ToString('HH:mm:ss.fff'), $isConsole, $w.cls, $sid, $w.pid, $proc, $w.title |
        Add-Content -LiteralPath $Out -Encoding UTF8
    }
  }
  if ((Get-Date) -ge $nextDuty) { Duty 'duty'; $nextDuty = (Get-Date).AddMilliseconds($DutyEveryMs) }
  Start-Sleep -Milliseconds $IntervalMs
}
Duty 'final'
"# window-watch end {0} : new windows={1}, new console-class windows={2}" -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $script:newCount, $script:newConsoleCount |
  Add-Content -LiteralPath $Out -Encoding UTF8
Write-Host ('window-watch: ' + $Out)

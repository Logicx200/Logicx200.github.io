# flash-probe.ps1 -- measure how long a visible console-class window lives while the
# interactive DshUsageWidget task starts (task-18 point 4).  Pure ASCII, BOM.
$ErrorActionPreference = 'Continue'
Add-Type -Namespace FL -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
public delegate bool EnumProc(IntPtr h, IntPtr p);
'@
function ConsoleWindows {
  $list = New-Object System.Collections.ArrayList
  $cb = [FL.U+EnumProc]{
    param($h, $p)
    if ([FL.U]::IsWindowVisible($h)) {
      $c = New-Object System.Text.StringBuilder 128
      [void][FL.U]::GetClassName($h, $c, 128)
      if ($c.ToString() -match 'Console|CASCADIA|PseudoConsole') {
        $wpid = [uint32]0
        [void][FL.U]::GetWindowThreadProcessId($h, [ref]$wpid)
        [void]$list.Add($c.ToString() + '/pid' + $wpid)
      }
    }
    return $true
  }
  [void][FL.U]::EnumWindows($cb, [IntPtr]::Zero)
  return $list
}
$base = @(ConsoleWindows)
$script:lines += ('  baseline visible console-class windows: ' + $base.Count + ' [' + ($base -join ', ') + ']')
$t0 = Get-Date
$peak = $base.Count
$everNew = @{}
while (((Get-Date) - $t0).TotalSeconds -lt 30) {
  $now = @(ConsoleWindows)
  if ($now.Count -gt $peak) {
    $peak = $now.Count
    $script:lines += ('  t+' + [math]::Round(((Get-Date) - $t0).TotalMilliseconds) + 'ms  console windows=' + $now.Count + ' [' + ($now -join ', ') + ']')
  }
  foreach ($w in $now) { $everNew[$w] = $true }
  Start-Sleep -Milliseconds 120
}
$script:lines += ('  peak during the 30 s window: ' + $peak + ' (baseline ' + $base.Count + ')')
$script:lines += ('  distinct console windows seen: ' + $everNew.Count)
$script:lines | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'flash-probe.txt') -Encoding UTF8

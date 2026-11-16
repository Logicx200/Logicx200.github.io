# interact-check.ps1 -- task-12 acceptance readings for the hit silhouette and the
# mouse interactions.  Pure ASCII (PS 5.1 reads a BOM-less .ps1 as ANSI).
#
#   A. WindowFromPoint at character points -> must be OUR window (ours(child))
#   B. WindowFromPoint at empty points     -> must be the window BELOW (OTHERS)
#   C. a real click on the body            -> the page must report it (interact.log)
#   D. a real right-click                  -> the menu must open (interact.log)
#   E. four quick clicks                   -> the rage tier must count up
#
# It never clicks a point that is not provably ours (that would hit the user's desktop).
param(
  [string]$Here = $PSScriptRoot,
  [string]$Out = (Join-Path $PSScriptRoot 'task12-interact-check.txt')
)
$ErrorActionPreference = 'Continue'
. (Join-Path $Here 'experiments\lib\win.ps1')

$modelPath = Join-Path $Here 'model.json'
$interactLog = Join-Path $Here 'interact.log'
$lines = New-Object System.Collections.ArrayList
function Say([string]$s) { [void]$lines.Add($s); Write-Host $s }

Say '=== task-12 hit silhouette + interactions ==='
if (-not (Test-Path -LiteralPath $modelPath)) { Say 'FAIL: model.json missing (host not running)'; $lines | Set-Content -LiteralPath $Out -Encoding UTF8; exit 1 }
$j = [System.IO.File]::ReadAllText($modelPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$win = $j.window
$bm = $j.screen.model
Say ("pet window  : {0},{1} {2}x{3}" -f $win.x, $win.y, $win.width, $win.height)
Say ("character   : {0},{1} .. {2},{3}" -f $bm.left, $bm.top, $bm.right, $bm.bottom)

# our top-level window handle: enumerate by title ("MainWindowHandle" is 0 for this
# window - ShowActivated=false and no taskbar entry - so walk the top-level windows)
$hostProc = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -match 'pet.host.host\.ps1' })
if ($hostProc.Count -lt 1) { Say 'FAIL: pet host process not found'; $lines | Set-Content -LiteralPath $Out -Encoding UTF8; exit 1 }
Add-Type -Namespace IC12 -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
public delegate bool EnumProc(IntPtr h, IntPtr p);
'@ -ErrorAction SilentlyContinue
$script:tgt = [IntPtr]::Zero
$cb = [IC12.U+EnumProc]{
  param($h, $p)
  $sb = New-Object System.Text.StringBuilder 128
  [void][IC12.U]::GetWindowText($h, $sb, 128)
  if ($sb.ToString() -eq 'DSH pet') { $script:tgt = $h }
  return $true
}
[void][IC12.U]::EnumWindows($cb, [IntPtr]::Zero)
Say ("host pid    : {0}" -f $hostProc[0].ProcessId)
Say ("our hwnd    : 0x{0:x}" -f [int64]$script:tgt)

$bx = [int](($bm.left + $bm.right) / 2); $by = [int]($bm.bottom - 45)
$hx = $bx; $hy = [int]($bm.top + 45)
$pts = @(
  @{ x = $hx; y = $hy; label = 'A1 head (character)'; want = 'ours' },
  @{ x = $bx; y = $by; label = 'A2 body (character)'; want = 'ours' },
  @{ x = $win.x + 6; y = $win.y + 6; label = 'B1 window top-left (empty)'; want = 'OTHERS' },
  @{ x = $win.x + 6; y = $win.y + $win.height - 6; label = 'B2 window bottom-left (empty)'; want = 'OTHERS' },
  @{ x = $win.x + $win.width - 6; y = $win.y + $win.height - 6; label = 'B3 window bottom-right (empty)'; want = 'OTHERS' }
)
$res = @()
foreach ($p in $pts) { $res += Test-ExpPoint -X $p.x -Y $p.y -Target $script:tgt -Label $p.label }
foreach ($r in $res) {
  $ok = if ($r.route -eq 'OTHERS') { 'OTHERS' } else { 'ours' }
  $verdict = if ($ok -eq 'ours') { 'ours' } else { 'OTHERS' }
  $want = ($pts | Where-Object { $_.label -eq $r.label }).want
  $mark = if ($verdict -eq $want) { 'ok  ' } else { 'FAIL' }
  Say ("{0} {1,-32} {2,5},{3,-5} route={4,-11} hit={5}" -f $mark, $r.label, $r.x, $r.y, $r.route, $r.hitClass)
}

# C/D/E: real input, only where the point is provably ours
Remove-Item -LiteralPath $interactLog -Force -ErrorAction SilentlyContinue
$body = $res | Where-Object { $_.label -eq 'A2 body (character)' }
$head = $res | Where-Object { $_.label -eq 'A1 head (character)' }
if ($body.isOurs) {
  Invoke-ExpClick -X $body.x -Y $body.y
  Start-Sleep -Milliseconds 600
  Say 'C  clicked the body once (poke)'
}
if ($head.isOurs) {
  1..4 | ForEach-Object { Invoke-ExpClick -X $head.x -Y $head.y; Start-Sleep -Milliseconds 200 }
  Start-Sleep -Milliseconds 400
  Say 'E  clicked the head four times quickly (rage tier)'
  [void][EXP.W]::SetCursorPos($head.x, $head.y)
  Start-Sleep -Milliseconds 120
  [EXP.W]::mouse_event(0x0008, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 40
  [EXP.W]::mouse_event(0x0010, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Seconds 2
  Say 'D  right-clicked the head (menu)'
} else {
  Say 'C/D/E SKIPPED: the character points are not ours (silhouette missing)'
}
Start-Sleep -Milliseconds 600
if (Test-Path -LiteralPath $interactLog) {
  $log = Get-Content -LiteralPath $interactLog | Select-Object -Last 12
  Say '--- page interaction receipts (pet\host\interact.log) ---'
  foreach ($l in $log) { Say $l }
} else {
  Say 'FAIL: no interaction receipts - the page received nothing'
}
$lines | Set-Content -LiteralPath $Out -Encoding UTF8
Write-Host ("interact-check: readings -> " + $Out)

# passthrough-check.ps1 -- task-13 acceptance: the pet window must be invisible to hit
# testing at EVERY point (whole-window click-through), so a desktop click always lands
# on whatever is behind her.  Pure ASCII (PS 5.1 reads a BOM-less .ps1 as ANSI).
param(
  [string]$Here = $PSScriptRoot,
  [string]$Out = (Join-Path $PSScriptRoot 'task13-passthrough.txt')
)
$ErrorActionPreference = 'Continue'
. (Join-Path $Here 'experiments\lib\win.ps1')

$modelPath = Join-Path $Here 'model.json'
$lines = New-Object System.Collections.ArrayList
function Say([string]$s) { [void]$lines.Add($s); Write-Host $s }

Say '=== task-13 whole-window click-through ==='
if (-not (Test-Path -LiteralPath $modelPath)) { Say 'FAIL: model.json missing (host not running)'; $lines | Set-Content -LiteralPath $Out -Encoding UTF8; exit 1 }
$j = [System.IO.File]::ReadAllText($modelPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$win = $j.window
$bm = $j.screen.model
Say ("pet window : {0},{1} {2}x{3}" -f $win.x, $win.y, $win.width, $win.height)
Say ("character  : {0},{1} .. {2},{3}" -f $bm.left, $bm.top, $bm.right, $bm.bottom)
Say ("host reports clickThrough = " + $j.clickThrough)

# our window handle: enumerate by title (ShowActivated=false gives no MainWindowHandle)
Add-Type -Namespace PT13 -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
public delegate bool EnumProc(IntPtr h, IntPtr p);
'@ -ErrorAction SilentlyContinue
$script:tgt = [IntPtr]::Zero
$cb = [PT13.U+EnumProc]{
  param($h, $p)
  $sb = New-Object System.Text.StringBuilder 128
  [void][PT13.U]::GetWindowText($h, $sb, 128)
  if ($sb.ToString() -eq 'DSH pet') { $script:tgt = $h }
  return $true
}
[void][PT13.U]::EnumWindows($cb, [IntPtr]::Zero)
Say ("our hwnd   : 0x{0:x}" -f [int64]$script:tgt)
$ex = [int64][EXP.W]::GetWindowLongPtr($script:tgt, -20)   # GWL_EXSTYLE
$transparent = (($ex -band 0x00000020) -ne 0)
Say ("WS_EX_TRANSPARENT = {0} (0x{1:x})" -f $transparent, $ex)

$cx = $win.x + [int]($win.width / 2)
$cy = $win.y + [int]($win.height / 2)
$pts = @(
  @{ x = [int](($bm.left + $bm.right) / 2); y = [int]($bm.top + 45); label = 'P1 head (character)' },
  @{ x = [int](($bm.left + $bm.right) / 2); y = [int]($bm.bottom - 45); label = 'P2 body (character)' },
  @{ x = $cx; y = $cy; label = 'P3 window centre' },
  @{ x = $win.x + 4; y = $win.y + 4; label = 'P4 window top-left' },
  @{ x = $win.x + $win.width - 4; y = $win.y + 4; label = 'P5 window top-right' },
  @{ x = $win.x + 4; y = $win.y + $win.height - 4; label = 'P6 window bottom-left' },
  @{ x = $win.x + $win.width - 4; y = $win.y + $win.height - 4; label = 'P7 window bottom-right' },
  @{ x = $cx; y = $win.y + 4; label = 'P8 window top-centre' },
  @{ x = $cx; y = $win.y + $win.height - 4; label = 'P9 window bottom-centre' },
  @{ x = $win.x + 4; y = $cy; label = 'P10 window left-centre' },
  @{ x = $win.x + $win.width - 4; y = $cy; label = 'P11 window right-centre' }
)
$ours = 0
foreach ($p in $pts) {
  $r = Test-ExpPoint -X $p.x -Y $p.y -Target $script:tgt -Label $p.label
  $mark = 'ok  '
  if ($r.route -ne 'OTHERS') { $mark = 'FAIL'; $ours += 1 }
  Say ("{0} {1,-24} {2,5},{3,-5} route={4,-11} hit={5}" -f $mark, $r.label, $r.x, $r.y, $r.route, $r.hitClass)
}
Say ''
Say ("points probed = {0} ; points that hit OUR window = {1}" -f $pts.Count, $ours)
if ($ours -eq 0) { Say 'RESULT: the pet window is fully click-through at every probed point' }
else { Say 'RESULT: FAIL - the pet window intercepts clicks somewhere' }
$lines | Set-Content -LiteralPath $Out -Encoding UTF8
Write-Host ('passthrough-check: readings -> ' + $Out)

# task16-shoot.ps1 -- task-15 §6.1 follow-up, FORENSICS ONLY (nothing in the production
# runtime or the geometry is touched).  Pure ASCII.
#
# Why a new shooter instead of pet\host\showcase-shoot.ps1: that script waits a fixed
# 1.6 s after forcing a state, which lands in the ramp-up of the 2.0~2.5 s motion clip and
# made the 11 images look alike.  This one captures a BURST around the clip's peak and
# lets the picker (pick_showcase.py) keep each state's most distinctive frame.
#
# payloads come from pet\showcase\states.json (the accepted showcase plan), so the states,
# labels and colours stay exactly what the docs describe.
param(
  [string]$OutDir = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\showcase\reactions-test\shoot-bursts'),
  [string]$Here = (Split-Path -Parent $PSScriptRoot),
  [string]$States = (Join-Path (Split-Path -Parent $PSScriptRoot) '..\showcase\states.json'),
  [int]$BurstFrames = 6,
  [int]$BurstGapMs = 260,
  [int]$PeakDelayMs = 1900
)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Get-ChildItem -LiteralPath $OutDir -Filter '*.png' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

$modelPath = Join-Path $Here 'model.json'
$forcePath = Join-Path $Here 'force-state.json'
if (-not (Test-Path -LiteralPath $modelPath)) { Write-Host 'FAIL: model.json missing (pet not running)'; exit 1 }
$j = [System.IO.File]::ReadAllText($modelPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$m = $j.screen.model
$pad = 0
$cx = [int]$m.left - $pad; $cy = [int]$m.top - $pad
$cw = [int]($m.right - $m.left) + 2 * $pad; $ch = [int]($m.bottom - $m.top) + 2 * $pad

$plan = [System.IO.File]::ReadAllText($States, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
Write-Host ('crop {0},{1} {2}x{3} ; {4} states from {5}' -f $cx, $cy, $cw, $ch, @($plan).Count, $States)

# two crops per shot: the tight character box is what the picker measures (crisp metric),
# the wide panel+character view is what pet\showcase ships (same framing as before).
$wideX = 1478; $wideY = 500; $wideW = 436; $wideH = 545
function Shot([string]$name) {
  $b = New-Object System.Drawing.Bitmap $cw, $ch
  $g = [System.Drawing.Graphics]::FromImage($b)
  $g.CopyFromScreen($cx, $cy, 0, 0, (New-Object System.Drawing.Size($cw, $ch)))
  $g.Dispose()
  $b.Save((Join-Path $OutDir ($name + '.png')), [System.Drawing.Imaging.ImageFormat]::Png)
  $b.Dispose()
  $w = New-Object System.Drawing.Bitmap $wideW, $wideH
  $g2 = [System.Drawing.Graphics]::FromImage($w)
  $g2.CopyFromScreen($wideX, $wideY, 0, 0, (New-Object System.Drawing.Size($wideW, $wideH)))
  $g2.Dispose()
  $w.Save((Join-Path $OutDir ($name + '-wide.png')), [System.Drawing.Imaging.ImageFormat]::Png)
  $w.Dispose()
}
function Force([string]$json) {
  [System.IO.File]::WriteAllText($forcePath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

# 1. idle reference burst (the baseline for both the picker and the report)
Force '{"state":"idle","pose":"idle","clearBubble":true}'
Start-Sleep -Milliseconds 2600
1..8 | ForEach-Object { Shot ('idle-{0:d2}' -f $_); Start-Sleep -Milliseconds 350 }
Write-Host 'idle reference burst captured'

# 2. every state: force, wait to the clip's peak, then burst a few frames
foreach ($s in $plan) {
  $payload = [ordered]@{ state = $s.state; label = $s.label; color = $s.color; pose = $s.pose; detail = $s.detail; clearBubble = $true }
  if ($s.signals) { $payload.signals = $s.signals }
  Force ($payload | ConvertTo-Json -Compress -Depth 6)
  Start-Sleep -Milliseconds $PeakDelayMs
  1..$BurstFrames | ForEach-Object { Shot ('{0}-{1:d2}' -f $s.state, $_); Start-Sleep -Milliseconds $BurstGapMs }
  Write-Host ('burst: {0} ({1}) pose={2}' -f $s.state, $s.label, $s.pose)
}

# 3. release the dev channel
Remove-Item -LiteralPath $forcePath -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 2200
Write-Host ('task16-shoot: bursts -> ' + $OutDir)
Write-Host ('force-state.json removed: ' + (-not (Test-Path -LiteralPath $forcePath)))

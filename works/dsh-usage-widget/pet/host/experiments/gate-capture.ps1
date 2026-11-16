# gate-capture.ps1 -- capture the frames the perceptual gate needs (task-15 E).
# Pure ASCII.  It forces `idle` for the baseline, then `running` (which now plays the
# splash motion) for the reaction, back to back so the panel behind her barely moves.
param(
  [string]$OutDir = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'showcase\reactions-test\gate-frames'),
  [string]$Here = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Get-ChildItem -LiteralPath $OutDir -Filter '*.png' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

$modelPath = Join-Path $Here 'model.json'
$forcePath = Join-Path $Here 'force-state.json'
if (-not (Test-Path -LiteralPath $modelPath)) { Write-Host 'FAIL: model.json missing'; exit 1 }
$j = [System.IO.File]::ReadAllText($modelPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$m = $j.screen.model
$pad = 6
$cx = [int]$m.left - $pad; $cy = [int]$m.top - $pad
$cw = [int]($m.right - $m.left) + 2 * $pad; $ch = [int]($m.bottom - $m.top) + 2 * $pad

function Shot([string]$name) {
  $b = New-Object System.Drawing.Bitmap $cw, $ch
  $g = [System.Drawing.Graphics]::FromImage($b)
  $g.CopyFromScreen($cx, $cy, 0, 0, (New-Object System.Drawing.Size($cw, $ch)))
  $g.Dispose()
  $b.Save((Join-Path $OutDir ($name + '.png')), [System.Drawing.Imaging.ImageFormat]::Png)
  $b.Dispose()
}
function Force([string]$json) {
  [System.IO.File]::WriteAllText($forcePath, $json, (New-Object System.Text.UTF8Encoding($false)))
  Start-Sleep -Milliseconds 2600
}

# baseline: idle held, 8 frames 350 ms apart
Force '{"state":"idle","pose":"idle","clearBubble":true}'
1..8 | ForEach-Object { Shot ('idle-{0:d2}' -f $_); Start-Sleep -Milliseconds 350 }
# reaction: running -> plays the splash clip; sample inside the clip
Force '{"state":"running","pose":"sleeves","clearBubble":true}'
Start-Sleep -Milliseconds 300; Shot 'reaction-0.3s'
Start-Sleep -Milliseconds 500; Shot 'reaction-0.8s'
Start-Sleep -Milliseconds 500; Shot 'reaction-1.3s'
Start-Sleep -Milliseconds 600; Shot 'reaction-1.9s'
# release the dev channel
Remove-Item -LiteralPath $forcePath -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 2400
Write-Host ('gate-capture: frames -> ' + $OutDir)

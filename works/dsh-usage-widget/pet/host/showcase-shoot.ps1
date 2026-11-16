# showcase-shoot.ps1 -- take the eleven state screenshots on the PRODUCTION geometry.
#
# For each state it rewrites pet\host\force-state.json, which the running production
# host (started by ui\widget.ps1) pushes into the page as
# `window.postMessage({type:'pet-force',payload})`.  The page's forced mode stops
# polling state.json / signals.json, so the engine's 2 s rewrites cannot steal the
# picture back; after the run the file goes away and the page returns to production.
#
# No second pet window is ever opened: it is the panel's own pet window, at its own
# position, with the real panel behind it.
#
# Pure ASCII on purpose: PS 5.1 reads a BOM-less .ps1 as ANSI (see
# pet/REACTIONS-SPEC.md section 10).  The Chinese labels live in
# pet/showcase/states.json and are read with an explicit UTF-8 decoder.
param(
  [string]$StatesFile = (Join-Path (Split-Path $PSScriptRoot -Parent) 'showcase\states.json'),
  [string]$OutDir = (Join-Path (Split-Path $PSScriptRoot -Parent) 'showcase'),
  [string]$ForceFile = (Join-Path $PSScriptRoot 'force-state.json'),
  [string]$Report = (Join-Path (Split-Path $PSScriptRoot -Parent) 'showcase\capture-report.txt'),
  # The crop has to hold the whole panel (it grows upwards from a pinned bottom) plus
  # the pet window.  Panel right/bottom = 1894/882, pet window = 1562,688 340x340.
  [int]$X = 1478,
  [int]$Y = 500,
  [int]$W = 436,
  [int]$H = 545,
  [int]$SettleMs = 1600,
  [int]$ShortSettleMs = 1400
)

Add-Type -AssemblyName System.Drawing

if (-not (Test-Path -LiteralPath $StatesFile)) { throw "states file not found: $StatesFile" }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$states = [System.IO.File]::ReadAllText($StatesFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
$short = @('error', 'celebrating', 'listening')   # TTL one-shots: shoot inside the TTL
$lines = New-Object System.Collections.ArrayList

function Save-Shot([string]$path) {
  $bmp = New-Object System.Drawing.Bitmap $W, $H
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size($W, $H)))
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}

foreach ($row in $states) {
  $payload = [ordered]@{
    state  = [string]$row.state
    label  = [string]$row.label
    color  = [string]$row.color
    pose   = [string]$row.pose
    detail = [string]$row.detail
    reason = [string]$row.reason
    signals = $row.signals
    # each shot must carry only its own dialogue, so the page clears the bubble first
    clearBubble = $true
  }
  $json = ($payload | ConvertTo-Json -Depth 8 -Compress)
  # every injected signal timestamp is 0 in states.json: make it "just now" so the
  # TTL states (error / celebrating / listening) actually light up.
  $nowMs = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
  $json = $json.Replace('"at":0', '"at":' + $nowMs)
  [System.IO.File]::WriteAllText($ForceFile, $json, (New-Object System.Text.UTF8Encoding($false)))
  $settle = if ($short -contains [string]$row.state) { $ShortSettleMs } else { $SettleMs }
  Start-Sleep -Milliseconds $settle
  $png = Join-Path $OutDir ('state-{0}.png' -f [string]$row.state)
  Save-Shot $png
  $item = Get-Item -LiteralPath $png
  $line = '{0} | {1} | {2} | pose={3} | detail="{4}" | reason="{5}" | {6}x{7} | {8} KB' -f `
    $row.state, $row.label, $row.color, $row.pose, $row.detail, $row.reason, $W, $H, [math]::Round($item.Length / 1024)
  [void]$lines.Add($line)
  Write-Host $line
}

# ---- restore: drop the force file, the host then pushes payload=null once -------
Remove-Item -LiteralPath $ForceFile -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 900
$lines | Set-Content -LiteralPath $Report -Encoding UTF8
Write-Host ('showcase-shoot: {0} shots -> {1} (report: {2})' -f @($states).Count, $OutDir, $Report)

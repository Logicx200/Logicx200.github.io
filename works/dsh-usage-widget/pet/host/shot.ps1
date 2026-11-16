# shot.ps1 -- capture part of the screen to a PNG (integration evidence). Pure ASCII.
#
#   powershell -NoProfile -File pet\host\shot.ps1 -X 1250 -Y 520 -W 670 -H 520 -Out pet\host\shot.png
#   powershell -NoProfile -File pet\host\shot.ps1 -All 1 -Out pet\host\desktop.png
param(
  [int]$X = 0,
  [int]$Y = 0,
  [int]$W = 800,
  [int]$H = 600,
  [int]$All = 0,
  [int]$DelayMs = 0,
  [string]$Out = ''
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
if ($All) {
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $X = $b.X; $Y = $b.Y; $W = $b.Width; $H = $b.Height
}
if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
if (-not $Out) { $Out = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'shot.png' }
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size($W, $H)))
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Host ("saved {0} ({1}x{2} at {3},{4})" -f $Out, $W, $H, $X, $Y)

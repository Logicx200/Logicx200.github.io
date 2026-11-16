# shot.ps1 -- capture a screen rectangle to a PNG. Pure ASCII on purpose (see run-pet.ps1 header).
#   .\shot.ps1 -X 0 -Y 0 -W 700 -H 650 -Out C:\tmp\a.png
param(
  [int]$X = 0, [int]$Y = 0, [int]$W = 700, [int]$H = 650,
  [string]$Out = 'shot.png'
)
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size $W, $H))
$full = [IO.Path]::GetFullPath($Out)
$dir = Split-Path -Parent $full
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$bmp.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "[shot] $full  ($W x $H from $X,$Y)"

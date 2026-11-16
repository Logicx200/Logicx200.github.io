# c1-run.ps1 -- run EXPERIMENT C1: start the alpha=1 WPF window, probe WindowFromPoint at four
# predictable points (alpha=1 rect / alpha=0 rect / opaque rect / empty area), screenshot, report.
# PURE ASCII.
param([int]$Hold = 30)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here '..\lib\win.ps1')

$info = Join-Path $here 'c1.json'
$shotDir = Join-Path $here '..\shots'
Remove-Item $info -Force -ErrorAction SilentlyContinue

Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-File', (Join-Path $here 'c1-show.ps1'),
  '-X', '60', '-Y', '60', '-W', '420', '-H', '300', '-Hold', "$Hold", '-Info', $info) | Out-Null

$deadline = (Get-Date).AddSeconds(20)
while (-not (Test-Path $info) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
if (-not (Test-Path $info)) { Write-Host 'FAILED: window never reported'; exit 1 }

$j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json
$target = [IntPtr][int64]$j.hwnd
Write-Host ("C1 window hwnd=0x{0:x} at {1},{2} {3}x{4} allowsTransparency={5}" -f $j.hwnd, $j.x, $j.y, $j.w, $j.h, $j.allowsTransparency)
Start-Sleep -Seconds 2

$pts = @(
  (Test-ExpPoint -X $j.probes.alpha1.x -Y $j.probes.alpha1.y -Target $target -Label 'A alpha=1/255'),
  (Test-ExpPoint -X $j.probes.alpha0.x -Y $j.probes.alpha0.y -Target $target -Label 'B alpha=0'),
  (Test-ExpPoint -X $j.probes.opaque.x -Y $j.probes.opaque.y -Target $target -Label 'C opaque'),
  (Test-ExpPoint -X $j.probes.empty.x  -Y $j.probes.empty.y  -Target $target -Label 'D empty area')
)
Write-Host ''
Write-Host '=== WindowFromPoint results ==='
Show-ExpPoints $pts | Write-Host

$png = Get-ExpShot -X ($j.x - 20) -Y ($j.y - 20) -W ($j.w + 40) -H ($j.h + 40) -Out (Join-Path $shotDir 'c1-wpf-alpha.png')
Write-Host "screenshot: $png"
Write-Host ''
Write-Host '=== verdict ==='
foreach ($p in $pts) {
  $expect = switch ($p.label) {
    'A alpha=1/255' { 'ours' }
    'C opaque'      { 'ours' }
    default         { 'OTHERS' }
  }
  $got = $(if ($p.isOurs) { 'ours' } else { 'OTHERS' })
  $mark = $(if ($expect -eq $got) { 'PASS' } else { 'FAIL' })
  Write-Host ("  {0,-16} expect={1,-6} got={2,-6} {3}   hit={4} ({5})" -f $p.label, $expect, $got, $mark, $p.hit, $p.hitClass)
}
$pts | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $here 'c1-result.json') -Encoding UTF8

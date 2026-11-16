# b-run.ps1 -- run EXPERIMENT B (colour-key layering) and report. PURE ASCII.
param([int]$Hold = 40)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here '..\lib\win.ps1')

$info = Join-Path $here 'b.json'
$shotDir = Join-Path $here '..\shots'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like '*b-show.ps1*' } |
  ForEach-Object { Write-Host "killing leftover B window pid $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
Remove-Item $info -Force -ErrorAction SilentlyContinue

Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-File', (Join-Path $here 'b-show.ps1'),
  '-X', '60', '-Y', '60', '-W', '520', '-H', '320', '-Hold', "$Hold", '-Info', $info) | Out-Null

$deadline = (Get-Date).AddSeconds(30)
while (-not (Test-Path $info) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }
if (-not (Test-Path $info)) { Write-Host 'FAILED: window never reported'; Get-Content (Join-Path $here 'b-show.log') -Encoding UTF8; exit 1 }

$j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json
$target = [IntPtr][int64]$j.hwnd
Write-Host ("B window hwnd=0x{0:x} at {1},{2} {3}x{4}  colourKeyApplied={5} key={6}" -f $j.hwnd, $j.x, $j.y, $j.w, $j.h, $j.colorKeyApplied, $j.layeredKey)
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
  $j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json
  if ($j.messageCount -ge 1) { break }
  Start-Sleep -Milliseconds 400
}
Write-Host ("page bridge: messages={0}" -f $j.messageCount)

$q1 = Test-ExpPoint -X $j.probes.q1_parent_magenta.x -Y $j.probes.q1_parent_magenta.y -Target $target -Label 'Q1 parent magenta'
$q2 = Test-ExpPoint -X $j.probes.q2_parent_green.x   -Y $j.probes.q2_parent_green.y   -Target $target -Label 'Q2 parent green'
$q3 = Test-ExpPoint -X $j.probes.q3_child_magenta.x  -Y $j.probes.q3_child_magenta.y  -Target $target -Label 'Q3 child magenta'
$q4 = Test-ExpPoint -X $j.probes.q4_child_blue.x     -Y $j.probes.q4_child_blue.y     -Target $target -Label 'Q4 child blue'
Write-Host ''
Write-Host '=== WindowFromPoint results ==='
Show-ExpPoints @($q1, $q2, $q3, $q4) | Write-Host

$before = (Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json).pageClicks
$clicked = $false
if ($q4.isOurs) { Invoke-ExpClick -X $q4.x -Y $q4.y; $clicked = $true; Start-Sleep -Seconds 2 }
$after = (Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json).pageClicks
Write-Host ("page __clicks: {0} -> {1}   (click injected at Q4: {2})" -f $before, $after, $clicked)

$png = Get-ExpShot -X ($j.x - 20) -Y ($j.y - 20) -W ($j.w + 40) -H ($j.h + 40) -Out (Join-Path $shotDir 'b-colorkey.png')
Write-Host "screenshot: $png"
Write-Host ''
Write-Host '=== verdict ==='
Write-Host ("  Q1 parent magenta : route={0}   (expect OTHERS if the key punches magenta out)" -f $q1.route)
Write-Host ("  Q2 parent green   : route={0}   (expect ours)" -f $q2.route)
Write-Host ("  Q3 child  magenta : route={0}   (expect OTHERS if the key also affects WebView2)" -f $q3.route)
Write-Host ("  Q4 child  blue    : route={0}   (expect ours)" -f $q4.route)
@{
  q1 = $q1; q2 = $q2; q3 = $q3; q4 = $q4; pageClicksBefore = $before; pageClicksAfter = $after
} | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $here 'b-result.json') -Encoding UTF8

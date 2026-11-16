# c2-run.ps1 -- run EXPERIMENT C2 and report, from the PAGE's point of view, whether a click arrives.
# PURE ASCII.
param([int]$Hold = 45)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here '..\lib\win.ps1')

$info = Join-Path $here 'c2.json'
$shotDir = Join-Path $here '..\shots'

# Kill any leftover window from a previous run: otherwise the old process keeps rewriting c2.json
# with its own (stale) hwnd and every probe silently targets the wrong window. This bug cost me a
# full re-run.
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like '*c2-show.ps1*' } |
  ForEach-Object { Write-Host "killing leftover C2 window pid $($_.ProcessId)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800
Remove-Item $info -Force -ErrorAction SilentlyContinue

Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-File', (Join-Path $here 'c2-show.ps1'),
  '-X', '60', '-Y', '60', '-W', '480', '-H', '320', '-Hold', "$Hold", '-Info', $info) | Out-Null

$deadline = (Get-Date).AddSeconds(30)
while (-not (Test-Path $info) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }
if (-not (Test-Path $info)) { Write-Host 'FAILED: window never reported'; Get-Content (Join-Path $here 'c2-show.log') -Encoding UTF8; exit 1 }

$j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json
$target = [IntPtr][int64]$j.hwnd
Write-Host ("C2 window hwnd=0x{0:x} at {1},{2} {3}x{4} allowsTransparency={5}" -f $j.hwnd, $j.x, $j.y, $j.w, $j.h, $j.allowsTransparency)

# wait until the page itself has phoned home, so we know the postMessage bridge works
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
  $j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json
  if ($j.messageCount -ge 1) { break }
  Start-Sleep -Milliseconds 400
}
Write-Host ("page bridge: messages={0} last={1}" -f $j.messageCount, $j.lastMessage)
if ($j.messageCount -lt 1) {
  Write-Host 'WARNING: page never phoned home -- the page-side click result will be UNRELIABLE'
  Get-Content (Join-Path $here 'c2-show.log') -Encoding UTF8 | Select-Object -Last 8
}

$p1 = Test-ExpPoint -X $j.probes.p1_page_opaque_and_alpha1.x -Y $j.probes.p1_page_opaque_and_alpha1.y -Target $target -Label 'P1 page-opaque + alpha1'
$p2 = Test-ExpPoint -X $j.probes.p2_alpha1_only.x            -Y $j.probes.p2_alpha1_only.y            -Target $target -Label 'P2 alpha=1 only'
$p3 = Test-ExpPoint -X $j.probes.p3_nothing.x                -Y $j.probes.p3_nothing.y                -Target $target -Label 'P3 nothing'
Write-Host ''
Write-Host '=== WindowFromPoint results ==='
Show-ExpPoints @($p1, $p2, $p3) | Write-Host

# --- real click, only where the point is provably ours (never click the user's desktop) ---
$before = (Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json).pageClicks
$clicked = $false
if ($p1.isOurs) {
  Invoke-ExpClick -X $p1.x -Y $p1.y
  $clicked = $true
  Start-Sleep -Seconds 2
}
$after = (Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json).pageClicks
Write-Host ''
Write-Host ("=== page-side click counter ===")
Write-Host ("  click injected at P1: {0}   page __clicks: {1} -> {2}" -f $clicked, $before, $after)

$png = Get-ExpShot -X ($j.x - 20) -Y ($j.y - 20) -W ($j.w + 40) -H ($j.h + 40) -Out (Join-Path $shotDir 'c2-wpf-webview2.png')
Write-Host "screenshot: $png"
Write-Host ''
Write-Host '=== verdict ==='
Write-Host ("  P1 page-opaque+alpha1 : route={0} hit={1} ({2})" -f $p1.route, $p1.hit, $p1.hitClass)
Write-Host ("  P2 alpha=1 only       : route={0} hit={1} ({2})" -f $p2.route, $p2.hit, $p2.hitClass)
Write-Host ("  P3 nothing            : route={0} hit={1} ({2})" -f $p3.route, $p3.hit, $p3.hitClass)
if ($clicked) {
  if ($after -gt $before) { Write-Host '  => THE PAGE RECEIVED THE CLICK (page counter increased) : PASS' }
  else { Write-Host '  => window was hit but THE PAGE GOT NOTHING (counter unchanged) : page NOT clickable' }
} else {
  Write-Host '  => window not hit at P1 either; click NOT injected (would have hit the desktop)'
}
@{
  p1 = $p1; p2 = $p2; p3 = $p3; pageClicksBefore = $before; pageClicksAfter = $after; clickInjected = $clicked
} | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $here 'c2-result.json') -Encoding UTF8

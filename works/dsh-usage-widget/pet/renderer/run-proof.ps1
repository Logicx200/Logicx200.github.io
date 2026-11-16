# run-proof.ps1 -- end-to-end transparency proof for the ELECTRON host, with hard evidence.
#
# NOTE: this needs host-electron\runtime\, which has been DELETED (the WebView2 host won and
# the 366 MB runtime was reclaimed -- see README.md sections 2 and 5). Use
# webview2-test\host-webview2.ps1 for the shipping route; this script is kept because it
# produces the click-through ON/OFF A/B that the WebView2 host cannot show.
#
# It runs the host twice (click-through ON and OFF) and for each run reports:
#   * the real HWND + window rect (from the app itself)
#   * extended window styles (WS_EX_TOPMOST / WS_EX_LAYERED / WS_EX_TRANSPARENT)
#   * what WindowFromPoint() hits at the middle of the pet -- i.e. who would receive a click
#   * a real screen capture
# Pure ASCII on purpose (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI and can swallow lines).
param(
  [int]$X = 1150, [int]$Y = 320, [int]$W = 440, [int]$H = 540,
  [string]$OutDir = 'F:\whale-chan-research\model',
  [int]$Hold = 40
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runPet = Join-Path $here 'host-electron\run-pet.ps1'
$shot = Join-Path $here 'shot.ps1'
$verify = Join-Path $here 'verify-window.ps1'
$runtimePrefix = Join-Path $here 'host-electron\runtime'

function Stop-Mine {
  Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and $_.Path.StartsWith($runtimePrefix) } catch { $false }
  } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}

function Run-One([int]$clickThrough, [string]$tag, [string]$png) {
  Write-Host ""
  Write-Host "==================== run: clickThrough=$clickThrough ===================="
  $log = Join-Path $OutDir "pet-boot-$tag.log"
  $info = Join-Path $OutDir "pet-info-$tag.json"
  Remove-Item $log, $info -Force -ErrorAction SilentlyContinue
  $env:PET_HOST_LOG = $log

  & $runPet -X $X -Y $Y -W $W -H $H -ClickThrough $clickThrough -AutoQuit ($Hold * 1000) -Info $info | Out-Null
  Start-Sleep -Seconds 10

  $j = $null
  if (Test-Path $info) { $j = Get-Content $info -Encoding UTF8 -Raw | ConvertFrom-Json }
  if (-not $j) { Write-Host "!! no info json -- page never came up"; Get-Content $log -Encoding UTF8 -Raw; return }

  Write-Host ("app says: hwnd={0} bounds={1},{2} {3}x{4} alwaysOnTop={5} clickThrough={6} pageReady={7} alphaProbe={8}" -f `
      $j.hwnd, $j.bounds.x, $j.bounds.y, $j.bounds.width, $j.bounds.height, $j.alwaysOnTop, $j.clickThrough, `
      $j.page.ready, ($j.page.alpha -join ','))

  $cx = $X + [int]($W / 2)
  $cy = $Y + [int]($H / 2)
  & $verify -Hwnd $j.hwnd -Point "$cx,$cy"

  & $shot -X ($X - 40) -Y ($Y - 40) -W ($W + 120) -H ($H + 120) -Out $png
  Stop-Mine
  Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Stop-Mine

Run-One 1 'ct-on'  (Join-Path $OutDir 'transparency-proof.png')
Run-One 0 'ct-off' (Join-Path $OutDir 'transparency-proof-clickthrough-off.png')

Write-Host ""
Write-Host "done. screenshots: transparency-proof.png / transparency-proof-clickthrough-off.png"

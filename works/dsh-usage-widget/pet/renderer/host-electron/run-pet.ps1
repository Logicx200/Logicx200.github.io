# run-pet.ps1 -- launch the transparent desktop-pet host (Electron runtime reused from DSH).
#
# STATUS: the WebView2 host (../webview2-test/host-webview2.ps1) won -- it gives the same
# per-pixel transparency without a 366 MB runtime. The runtime copy was therefore DELETED;
# only this app code is kept as a reference. To use this route again, recreate
# host-electron\runtime\ by copying these from D:\DeepSeek Harness\:
#   DeepSeek Harness.exe, *.dll, *.pak, *.dat, *.bin, locales\, resources\default_app.asar
# (NOT resources\app.asar -- Electron must fall back to default_app.asar + the argv app path,
#  and it will not do that while resources\app.asar exists.)
# See ../README.md section 5.
#
#   .\run-pet.ps1                                 default: bottom-right of the work area
#   .\run-pet.ps1 -X 1200 -Y 600                  explicit position
#   .\run-pet.ps1 -Panel "1000,500,1600,1000"     put ~1/4 of the pet inside this panel rect
#   .\run-pet.ps1 -ClickThrough 0                 disable click-through (to prove the window CAN take clicks)
#   .\run-pet.ps1 -AutoQuit 8000 -Info out.json   auto-exit after 8s, dump window info to json
#
# IMPORTANT -- KEEP THIS FILE PURE ASCII.
# Windows PowerShell 5.1 (and this shell) reads .ps1 as the system ANSI codepage (GBK here)
# unless the file carries a UTF-8 BOM. A UTF-8 Chinese comment then turns into mojibake and
# can swallow the following line, silently disabling code. That bug cost a full debug cycle:
# the Remove-Item below was eaten by the comment above it and the exe started as Node.
param(
  [int]$X = [int]::MinValue, [int]$Y = [int]::MinValue,
  [int]$W = 460, [int]$H = 560,
  [int]$ClickThrough = 1,
  [int]$AlwaysOnTop = 1,
  [int]$Resizable = 0,
  [string]$Panel = '',
  [int]$AutoQuit = 0,
  [string]$Info = '',
  [string]$Q = '',
  [string]$UserData = '',
  [switch]$Wait
)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $here 'runtime\DeepSeek Harness.exe'
$appDir = Join-Path $here 'app'

# DSH exports ELECTRON_RUN_AS_NODE=1 to every child process. If it survives, our exe degrades
# into a plain Node interpreter ("Cannot find module 'electron'") and exits at once.
if (Test-Path Env:\ELECTRON_RUN_AS_NODE) { Remove-Item Env:\ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue }
if (Test-Path Env:\ELECTRON_NO_ATTACH_CONSOLE) { Remove-Item Env:\ELECTRON_NO_ATTACH_CONSOLE -ErrorAction SilentlyContinue }

if (-not (Test-Path $exe)) { throw "Electron runtime not found: $exe" }
if (-not (Test-Path (Join-Path $appDir 'main.js'))) { throw "host app not found: $appDir" }

# Keep Chromium's profile out of the real DSH profile: never share userData with the running app.
if (-not $UserData) { $UserData = Join-Path $here 'userdata' }
if (-not (Test-Path $UserData)) { New-Item -ItemType Directory -Force -Path $UserData | Out-Null }

# Pass a RELATIVE app path; absolute Chinese paths in argv are the risky case, and the child
# cwd is set through WorkingDirectory (a real Win32 attribute, not argv), so it survives.
$a = @('app', "--user-data-dir=$UserData", "--w=$W", "--h=$H",
       "--clickthrough=$ClickThrough", "--always-on-top=$AlwaysOnTop", "--resizable=$Resizable")
if ($X -ne [int]::MinValue) { $a += "--x=$X" }
if ($Y -ne [int]::MinValue) { $a += "--y=$Y" }
if ($Panel) { $a += "--panel=$Panel" }
if ($AutoQuit -gt 0) { $a += "--autoquit=$AutoQuit" }
if ($Info) { $a += "--info=$Info" }
if ($Q) { $a += "--q=$Q" }

Write-Host "[run-pet] ELECTRON_RUN_AS_NODE present = $(Test-Path Env:\ELECTRON_RUN_AS_NODE)"
Write-Host "[run-pet] cwd=$here exe=$exe app=app"
if ($Wait) {
  Push-Location $here
  & $exe @a
  Pop-Location
} else {
  Start-Process -FilePath $exe -ArgumentList $a -WorkingDirectory $here
}

# a-run.ps1 -- EXPERIMENT A: Electron transparent window.
#   * launch from the SYMLINKED dist (no 366 MB copy)
#   * measure startup (module load -> shown) and resident memory of the whole process tree
#   * measure hit testing with click-through ON and OFF, and whether the PAGE receives a real click
#   * screenshot in both modes
# PURE ASCII.
param([int]$X = 60, [int]$Y = 60, [int]$W = 460, [int]$H = 560, [int]$Hold = 55)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here '..\lib\win.ps1')

$dist = Join-Path $here 'dist'
$appDir = Join-Path $dist 'resources\app'
$state = Join-Path $appDir 'a-state.json'
$control = Join-Path $appDir 'a-control.json'
$userData = Join-Path $here 'userdata'
$shotDir = Join-Path $here '..\shots'

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like '*a-run.ps1*' -and $_.ProcessId -ne $PID } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { try { $_.Path -and $_.Path.StartsWith($dist) } catch { $false } } |
  ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { try { $_.Path -and $_.Path.StartsWith($dist) } catch { $false } } |
  ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 900
Remove-Item $state, "$state.tmp" -Force -ErrorAction SilentlyContinue
# Chromium keeps a lock inside the user-data-dir; a leftover instance from a previous run makes
# every later launch exit instantly. Clear it too.
Remove-Item $userData -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $userData | Out-Null
'{ "clickThrough": true }' | Set-Content -Path $control -Encoding ASCII

if (-not (Test-Path (Join-Path $dist 'DeepSeek Harness.exe'))) { Write-Host 'dist missing'; exit 1 }

# DSH exports ELECTRON_RUN_AS_NODE=1 to every child process. If it survives, the exe degrades into
# a plain Node interpreter and rejects our switches as "bad option: --x=60" -- exactly what
# happened on the first attempt at this experiment.
if (Test-Path Env:\ELECTRON_RUN_AS_NODE) { Remove-Item Env:\ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue }
if (Test-Path Env:\ELECTRON_NO_ATTACH_CONSOLE) { Remove-Item Env:\ELECTRON_NO_ATTACH_CONSOLE -ErrorAction SilentlyContinue }

Write-Host '=== launching symlinked Electron dist ==='
Write-Host ("  env: ELECTRON_RUN_AS_NODE present = {0}" -f (Test-Path Env:\ELECTRON_RUN_AS_NODE))
Write-Host ("  control file = {0}" -f $control)
$t = Get-Date
Start-Process -FilePath (Join-Path $dist 'DeepSeek Harness.exe') `
  -ArgumentList @("--x=$X", "--y=$Y", "--w=$W", "--h=$H", "--user-data-dir=$userData", "--autoquit=$($Hold * 1000)") `
  -WorkingDirectory $dist -RedirectStandardError (Join-Path $here 'a-stderr.txt') -RedirectStandardOutput (Join-Path $here 'a-stdout.txt') | Out-Null

Start-Sleep -Seconds 2
if (-not (Test-Path $state)) {
  Write-Host '  diagnostics after 8s:'
  Write-Host ("    state file exists : {0}" -f (Test-Path $state))
  Write-Host ("    dist processes    : {0}" -f (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue | Where-Object { try { $_.Path -and $_.Path.StartsWith($dist) } catch { $false } }).Count)
  Write-Host '    stderr:'
  Get-Content (Join-Path $here 'a-stderr.txt') -ErrorAction SilentlyContinue | Select-Object -First 8 | ForEach-Object { Write-Host ('      ' + $_) }
}

$deadline = (Get-Date).AddSeconds(30)
while (-not (Test-Path $state) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 150 }
if (-not (Test-Path $state)) { Write-Host 'FAILED: app never reported'; exit 1 }

$j = Get-Content $state -Encoding UTF8 -Raw | ConvertFrom-Json
$deadline = (Get-Date).AddSeconds(30)
while (-not $j.showAt -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 150; $j = Get-Content $state -Encoding UTF8 -Raw | ConvertFrom-Json }
$endToEnd = ((Get-Date) - $t).TotalMilliseconds
if (-not $j.showAt) { Write-Host ('FAILED: window never shown; error=' + $j.error); exit 1 }

$target = [IntPtr]::Zero
Write-Host ("app pid={0} electron={1}" -f $j.pid, $j.electron)
Write-Host ("execPath     = {0}" -f $j.execPath)
Write-Host ("resourcesPath= {0}" -f $j.resourcesPath)
Write-Host ("startup: in-process t0->shown = {0} ms ; wall-clock launch->shown = {1} ms" -f ($j.showAt - $j.t0), [int]$endToEnd)

# --- memory of the whole tree ---
function Get-TreePids([int]$Root) {
  $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Select-Object ProcessId, ParentProcessId
  $out = New-Object System.Collections.ArrayList
  [void]$out.Add($Root)
  $i = 0
  while ($i -lt $out.Count) {
    $pidCur = $out[$i]; $i++
    foreach ($c in ($all | Where-Object { $_.ParentProcessId -eq $pidCur })) { if (-not $out.Contains([int]$c.ProcessId)) { [void]$out.Add([int]$c.ProcessId) } }
  }
  return $out
}
$appPid = [int]$j.pid
$pids = Get-TreePids -Root $appPid
$mem = 0
foreach ($p in $pids) { $pr = Get-Process -Id $p -ErrorAction SilentlyContinue; if ($pr) { $mem += $pr.WorkingSet64 } }
Write-Host ("process tree: {0} processes ({1})" -f $pids.Count, ($pids -join ','))
Write-Host ("resident memory (working set, whole tree): {0} MB" -f [math]::Round($mem / 1MB, 1))

# The app reports its own native window handle -- far more reliable than MainWindowHandle guessing.
$hwnd = [IntPtr]::Zero
if ($j.hwnd) { $hwnd = [IntPtr][int64]::Parse(([string]$j.hwnd).Replace('0x', ''), [System.Globalization.NumberStyles]::HexNumber) }
Write-Host ("window hwnd = 0x{0:x} (title '{1}')" -f $hwnd.ToInt64(), (Get-ExpTitle $hwnd))

$dotX = $X + [int]($W / 2); $dotY = $Y + 220
$emptyX = $X + 30; $emptyY = $Y + $H - 20

function Probe-Both([string]$tag) {
  $a = Test-ExpPoint -X $dotX -Y $dotY -Target $hwnd -Label "$tag dot(opaque)"
  $b = Test-ExpPoint -X $emptyX -Y $emptyY -Target $hwnd -Label "$tag corner(transparent)"
  Write-Host ("  [{0}] dot -> {1} ({2})   corner -> {3} ({4})" -f $tag, $a.route, $a.hitClass, $b.route, $b.hitClass)
  return @($a, $b)
}

Write-Host ''
Write-Host '=== hit test: click-through ON (production default) ==='
$on = Probe-Both 'CT-ON'
$pngOn = Get-ExpShot -X ($X - 20) -Y ($Y - 20) -W ($W + 40) -H ($H + 40) -Out (Join-Path $shotDir 'a-electron-ct-on.png')

Write-Host '=== hit test: click-through OFF (flipped at runtime via control file) ==='
'{ "clickThrough": false }' | Set-Content -Path $control -Encoding ASCII
Start-Sleep -Seconds 2
$off = Probe-Both 'CT-OFF'

$clicksBefore = (Get-Content $state -Encoding UTF8 -Raw | ConvertFrom-Json).clicks
$clicked = $false
if ($off[0].isOurs) { Invoke-ExpClick -X $dotX -Y $dotY; $clicked = $true; Start-Sleep -Seconds 2 }
$clicksAfter = (Get-Content $state -Encoding UTF8 -Raw | ConvertFrom-Json).clicks
$pngOff = Get-ExpShot -X ($X - 20) -Y ($Y - 20) -W ($W + 40) -H ($H + 40) -Out (Join-Path $shotDir 'a-electron-ct-off.png')

Write-Host ''
Write-Host ("page clicks: {0} -> {1}  (real click injected at the dot: {2})" -f $clicksBefore, $clicksAfter, $clicked)
Write-Host "screenshots: $pngOn / $pngOff"

# also try the corner with a click in CT-OFF mode: it should still fall through
$cornerClick = $false
if ($off[1].isOurs) { Write-Host '  NOTE: corner is also ours in CT-OFF (whole rectangle clickable)'; $cornerClick = $true } else { Write-Host '  corner still passes through in CT-OFF: TRUE' }

Write-Host ''
Write-Host '=== verdict ==='
Write-Host ("  CT-ON  : dot={0} corner={1}  (expect OTHERS/OTHERS = fully click-through)" -f $on[0].route, $on[1].route)
Write-Host ("  CT-OFF : dot={0} corner={1}" -f $off[0].route, $off[1].route)
if ($clicked -and $clicksAfter -gt $clicksBefore) { Write-Host '  => THE PAGE RECEIVED THE CLICK : PASS' }
elseif ($clicked) { Write-Host '  => window hit but page got nothing : FAIL' }
else { Write-Host '  => window never hit at the dot in CT-OFF either : FAIL' }

@{
  state = $j; startupMsInProcess = ($j.showAt - $j.t0); startupMsWallClock = [int]$endToEnd
  treePids = $pids; memMB = [math]::Round($mem / 1MB, 1)
  ctOn = $on; ctOff = $off; clicksBefore = $clicksBefore; clicksAfter = $clicksAfter
} | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $here 'a-result.json') -Encoding UTF8

# --- shutdown ---
'{ "clickThrough": true, "quit": true }' | Set-Content -Path $control -Encoding ASCII
Start-Sleep -Seconds 3
Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { try { $_.Path -and $_.Path.StartsWith($dist) } catch { $false } } |
  ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Write-Host 'app stopped'

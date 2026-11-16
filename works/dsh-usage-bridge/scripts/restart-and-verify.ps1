<#
.SYNOPSIS
Restart DeepSeek Harness and verify that the usage bridge loaded.

.DESCRIPTION
The bridge is a host-side DSH plugin. A host plugin's source is cached by the
loader for the life of the process, so a fixed bridge only takes effect after the
application restarts — that is the whole reason this script exists.

After the restart it proves the bridge is alive in the cheapest way possible: the
plugin writes `jobs.json` unconditionally on its first tick, even when the
registry reports no jobs, so the file existing at all means the plugin loaded and
is ticking. It then captures the widget's corner of the screen so the sections it
drives can be inspected without another round trip.

Launch it from OUTSIDE the application's process tree (Task Scheduler or WMI): it
kills the application, including any agent session hosted by it.

.PARAMETER DelaySeconds
Wait this long before restarting, so a caller can finish its turn first.
#>
[CmdletBinding()]
param(
  [string]$App = 'D:\DeepSeek Harness\DeepSeek Harness.exe',
  [int]$Port = 19387,
  [int]$DelaySeconds = 0,
  [int]$BootTimeoutSeconds = 180,
  [string]$Log = '',
  [string]$RemoveTask = ''
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $here 'bridge-report.txt' }
$Log = [System.IO.Path]::GetFullPath($Log)

function Say {
  param([string]$Line)
  $text = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Line
  Write-Host $text
  try { Add-Content -LiteralPath $Log -Value $text -Encoding UTF8 } catch { }
}

Add-Type -AssemblyName System.Drawing

Say ('bridge-verify: begin  session={0}  delay={1}s' -f [System.Diagnostics.Process]::GetCurrentProcess().SessionId, $DelaySeconds)
if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }

# 1. restart ---------------------------------------------------------------
$before = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
Say ('stopping {0} application process(es)' -f $before.Count)
foreach ($process in $before) { try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { } }
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)) {
  Start-Sleep -Milliseconds 500
}
Say "starting $App"
Start-Process -FilePath $App | Out-Null

$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
$up = $false
while ((Get-Date) -lt $deadline) {
  $ids = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
  foreach ($processId in $ids) {
    if (Get-NetTCPConnection -State Listen -OwningProcess $processId -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port }) { $up = $true; break }
  }
  if ($up) { break }
  Start-Sleep -Seconds 2
}
if (-not $up) {
  Say "FAILED: the GUI never listened on $Port"
  if ($RemoveTask -ne '') { try { Unregister-ScheduledTask -TaskName $RemoveTask -Confirm:$false -ErrorAction Stop } catch { } }
  exit 1
}
Say "GUI is up on $Port; waiting 25s for plugins and the first bridge tick"
Start-Sleep -Seconds 25

# 2. is the bridge alive? --------------------------------------------------
$state = Join-Path (Join-Path $env:USERPROFILE '.dsh') 'usage-widget\jobs.json'
Say ''
Say "--- bridge state file: $state"
if (Test-Path -LiteralPath $state) {
  $info = Get-Item -LiteralPath $state
  Say ("EXISTS  {0} bytes  written {1}" -f $info.Length, $info.LastWriteTime.ToString('HH:mm:ss'))
  try {
    $parsed = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
    Say ("parsed  at={0}  jobs={1}" -f $parsed.at, @($parsed.jobs).Count)
    foreach ($job in @($parsed.jobs)) {
      Say ("  job  {0}  {1}  {2}  percent={3}  eta={4}  last={5}" -f `
          $job.id, $job.kind, $job.label, $job.percent, $job.etaMs, $job.lastLine)
    }
    Say 'VERDICT: the bridge is ALIVE (it wrote its beacon)'
  } catch {
    Say "the file exists but did not parse: $($_.Exception.Message)"
    Say 'VERDICT: bridge wrote something malformed'
  }
} else {
  Say 'MISSING — the bridge did not write its beacon'
  Say 'VERDICT: the bridge is still NOT loading (check the loader entry phase)'
}

# 3. what the widget shows -------------------------------------------------
Say ''
$shot = Join-Path $here 'bridge-after-restart.png'
try {
  $bmp = New-Object System.Drawing.Bitmap 1920, 1032
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
  $g.Dispose()
  $crop = New-Object System.Drawing.Bitmap 500, 300
  $g2 = [System.Drawing.Graphics]::FromImage($crop)
  $g2.DrawImage($bmp, (New-Object System.Drawing.Rectangle 0, 0, 500, 300),
    (New-Object System.Drawing.Rectangle 1420, 732, 500, 300), [System.Drawing.GraphicsUnit]::Pixel)
  $crop.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
  $g2.Dispose(); $crop.Dispose(); $bmp.Dispose()
  Say "widget capture: $shot"
} catch {
  Say "capture failed: $($_.Exception.Message)"
}

$widget = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*-File*widget.ps1*' })
Say ("widget instances running: {0}" -f $widget.Count)

Say 'bridge-verify: done'

if ($RemoveTask -ne '') {
  try {
    Unregister-ScheduledTask -TaskName $RemoveTask -Confirm:$false -ErrorAction Stop
    Say "removed the one-shot task $RemoveTask"
  } catch {
    Say "could not remove the one-shot task $RemoveTask : $($_.Exception.Message)"
  }
}

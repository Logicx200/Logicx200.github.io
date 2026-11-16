<#
.SYNOPSIS
Decide whether "create a new session blanks the conversation panel" is caused by
the usage-dashboard plugin, then leave the application usable.

.DESCRIPTION
The failure looks like this: creating a new session leaves the whole main region
empty. Every session-scoped slot is dead (the conversation panel and the right
sidebar), while root-scoped panels - the Plugins page - still render. That is the
signature of a lost session scope binding, and the shell rethrows
`SlotAssemblyError` past its slot boundary rather than showing a crash face.

Evidence already gathered interactively: with this plugin's slot registrations
verified as unloaded (the client Slots inspector listed the occupants of
`sidebar.right.pane.tab` and `conversation.session.header.actions` without it),
switching the main panel away and back - a fresh mount, because `main` is a keyed
slot - still rendered blank. That points away from the plugin, but the state was
already broken when that was observed.

This script removes the ambiguity by restarting from a clean process:

  1. restart the application,
  2. measure the main region before touching anything,
  3. click the sidebar's "new session" button,
  4. measure again and decide,
  5. restart once more, so the application is left in a working state either way.

Measurements are pixel statistics over the main region, and both screenshots are
kept beside the report.

Launch this from OUTSIDE the application's process tree (Task Scheduler or WMI):
it kills the application, including any agent session hosted by it.

.PARAMETER DelaySeconds
Wait this long before the first restart, so a caller can finish its turn.
#>
[CmdletBinding()]
param(
  [string]$App = 'D:\DeepSeek Harness\DeepSeek Harness.exe',
  [int]$Port = 19387,
  [int]$DelaySeconds = 0,
  [int]$BootTimeoutSeconds = 180,
  [int]$NewSessionX = 140,
  [int]$NewSessionY = 111,
  [string]$Log = '',
  [string]$RemoveTask = '',
  [switch]$ReenableBundle
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $here 'blank-probe-report.txt' }
$Log = [System.IO.Path]::GetFullPath($Log)

function Say {
  param([string]$Line)
  $text = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Line
  Write-Host $text
  try { Add-Content -LiteralPath $Log -Value $text -Encoding UTF8 } catch { }
}

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ProbeNative {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  public const uint DOWN = 0x0002, UP = 0x0004;
}
"@

function Save-Shot {
  param([string]$Path)
  $bmp = New-Object System.Drawing.Bitmap 1920, 1032
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
  $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose()
  return $bmp
}

<#
 Sample the main region and report how much it varies. A rendered conversation
 is text on a dark field; a blank panel is one flat colour. Both the distinct
 colour count and the luminance spread separate the two by a wide margin.
#>
function Measure-MainRegion {
  param([System.Drawing.Bitmap]$Bitmap)
  $colors = New-Object 'System.Collections.Generic.HashSet[int]'
  $values = New-Object 'System.Collections.Generic.List[double]'
  for ($x = 320; $x -lt 1800; $x += 16) {
    for ($y = 120; $y -lt 900; $y += 16) {
      $pixel = $Bitmap.GetPixel($x, $y)
      [void]$colors.Add(($pixel.R -shl 16) -bor ($pixel.G -shl 8) -bor $pixel.B)
      $values.Add(0.299 * $pixel.R + 0.587 * $pixel.G + 0.114 * $pixel.B)
    }
  }
  $mean = ($values | Measure-Object -Average).Average
  $sum = 0.0
  foreach ($value in $values) { $sum += ($value - $mean) * ($value - $mean) }
  $sd = [Math]::Sqrt($sum / [Math]::Max(1, $values.Count))
  return [pscustomobject]@{ colors = $colors.Count; sd = [Math]::Round($sd, 2) }
}

function Restart-App {
  $before = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
  Say ('restart: stopping {0} process(es)' -f $before.Count)
  foreach ($process in $before) { try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { } }
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline -and (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)) {
    Start-Sleep -Milliseconds 500
  }
  Say "restart: starting $App"
  Start-Process -FilePath $App | Out-Null
  $deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $ids = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    foreach ($processId in $ids) {
      if (Get-NetTCPConnection -State Listen -OwningProcess $processId -ErrorAction SilentlyContinue |
          Where-Object { $_.LocalPort -eq $Port }) {
        Say "restart: GUI listening on $Port"
        Start-Sleep -Seconds 12   # let the client finish composing and the sweep land
        return $true
      }
    }
    Start-Sleep -Seconds 2
  }
  Say "restart: FAILED, no listener on $Port within $BootTimeoutSeconds s"
  return $false
}

Say ('blank-probe: begin  session={0}  delay={1}s  app={2}' -f [System.Diagnostics.Process]::GetCurrentProcess().SessionId, $DelaySeconds, $App)
if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }

if (-not (Restart-App)) { Say 'blank-probe: aborting'; exit 1 }

$window = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($window) { [ProbeNative]::SetForegroundWindow($window.MainWindowHandle) | Out-Null; Start-Sleep -Milliseconds 600 }

$beforePath = Join-Path $here 'blank-probe-before.png'
$bmp = Save-Shot -Path $beforePath
$before = Measure-MainRegion -Bitmap $bmp
$bmp.Dispose()
Say ('baseline: main region colors={0} luminanceSd={1}  ({2})' -f $before.colors, $before.sd, $beforePath)

Say ('clicking the sidebar new-session button at ({0},{1})' -f $NewSessionX, $NewSessionY)
[ProbeNative]::SetCursorPos($NewSessionX, $NewSessionY) | Out-Null
Start-Sleep -Milliseconds 300
[ProbeNative]::mouse_event([ProbeNative]::DOWN, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Milliseconds 60
[ProbeNative]::mouse_event([ProbeNative]::UP, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Seconds 6

$afterPath = Join-Path $here 'blank-probe-after.png'
$bmp = Save-Shot -Path $afterPath
$after = Measure-MainRegion -Bitmap $bmp
$bmp.Dispose()
Say ('after new session: main region colors={0} luminanceSd={1}  ({2})' -f $after.colors, $after.sd, $afterPath)

# A blank panel is one flat colour: few distinct colours and almost no spread.
# A rendered conversation carries hundreds of colours and a spread in the teens.
$blank = ($after.colors -lt 20) -or ($after.sd -lt 2.0)
if ($blank) {
  Say 'VERDICT: BLANK - creating a new session empties the main region, and this plugin is NOT installed in this run.'
  Say '         The defect is in the application, not in dsh-usage-dashboard.'
} else {
  Say 'VERDICT: RENDERED - the new session drew normally in this run.'
  Say '         The earlier blank state was not reproducible from a clean boot.'
}
if ($before.colors -lt 20) { Say 'NOTE: the baseline was already blank, so the run proves nothing about the click.' }

<#
 Put the dashboard back into the desktop profile's bundle list, so the final
 restart brings the application up in the configuration the user actually wants.
 The probe itself must run without it, otherwise a blank result cannot separate
 the plugin from the application.
#>
function Enable-Bundle {
  $pkg = Join-Path $env:USERPROFILE '.dsh\profiles\desktop\package.json'
  $raw = [System.IO.File]::ReadAllText($pkg)
  if ($raw -match 'dsh-usage-dashboard') {
    Say 'bundle: dsh-usage-dashboard is already listed'
    return
  }
  $with = $raw -replace '("@deepseek-ai/dsh-experimental-schedule-bundle")', "`$1,`r`n        `"dsh-usage-dashboard`""
  [System.IO.File]::WriteAllText($pkg, $with, (New-Object System.Text.UTF8Encoding($false)))
  Say 'bundle: dsh-usage-dashboard restored to dsh.profile.bundles'
}

if ($ReenableBundle) { Enable-Bundle }

Say 'restarting once more so the application is left usable'
[void](Restart-App)
Say 'blank-probe: done'

if ($RemoveTask -ne '') {
  try {
    Unregister-ScheduledTask -TaskName $RemoveTask -Confirm:$false -ErrorAction Stop
    Say "removed the one-shot task $RemoveTask"
  } catch {
    Say "could not remove the one-shot task $RemoveTask : $($_.Exception.Message)"
  }
}

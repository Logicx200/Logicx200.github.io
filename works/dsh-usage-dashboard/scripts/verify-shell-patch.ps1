<#
.SYNOPSIS
Verify the shell slot-boundary patch against a fresh boot.

.DESCRIPTION
`scripts/patch-shell-slot-boundary.mjs` turns the shell's two slot error
boundaries from "rethrow a SlotAssemblyError past everything" into "contain it
like any other slot failure". The patch only reaches a page that boots after it
was written, so this script:

  1. restarts the application,
  2. waits until the dashboard's diagnostic is live (it re-asserts the window
     title every 500 ms, so a title starting with `DIAG` proves the client half
     loaded and the capture is armed),
  3. measures the main region before touching anything,
  4. clicks the sidebar's new-session button - the exact action that used to
     blank the conversation panel and the session-scoped sidebar,
  5. captures the window title again, which now carries whatever the shell
     reported through `console.error` (including the slot key of any contained
     failure), and measures the main region again,
  6. restarts once more only if the region came back blank, so the application is
     always left usable.

Launch it from OUTSIDE the application's process tree (Task Scheduler or WMI):
it kills the application, including any agent session hosted by it.
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
  [string]$RemoveTask = ''
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $here 'shell-patch-report.txt' }
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
public class ShellPatchNative {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  public const uint DOWN = 0x0002, UP = 0x0004;
}
"@

function Get-GuiTitle {
  $process = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -First 1
  if ($process) { return $process.MainWindowTitle }
  return ''
}

function Save-Screenshot {
  param([string]$Path)
  $bmp = New-Object System.Drawing.Bitmap 1920, 1032
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
  $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose()
  return $bmp
}

<#
 Sample the main region. A rendered conversation is text on a dark field; a blank
 panel is one flat colour, so the distinct colour count separates them widely.
#>
function Measure-MainRegion {
  param([System.Drawing.Bitmap]$Bitmap)
  $colors = New-Object 'System.Collections.Generic.HashSet[int]'
  for ($x = 320; $x -lt 1800; $x += 16) {
    for ($y = 120; $y -lt 900; $y += 16) {
      $pixel = $Bitmap.GetPixel($x, $y)
      [void]$colors.Add(($pixel.R -shl 16) -bor ($pixel.G -shl 8) -bor $pixel.B)
    }
  }
  return $colors.Count
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
        Start-Sleep -Seconds 15   # client composition + diagnostic install
        return $true
      }
    }
    Start-Sleep -Seconds 2
  }
  Say "restart: FAILED, no listener on $Port within $BootTimeoutSeconds s"
  return $false
}

Say ('shell-patch: begin  session={0}  delay={1}s' -f [System.Diagnostics.Process]::GetCurrentProcess().SessionId, $DelaySeconds)
if ($DelaySeconds -gt 0) { Start-Sleep -Seconds $DelaySeconds }

if (-not (Restart-App)) { Say 'shell-patch: aborting'; exit 1 }

$window = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($window) { [ShellPatchNative]::SetForegroundWindow($window.MainWindowHandle) | Out-Null; Start-Sleep -Milliseconds 600 }

Say ''
Say '--- before ---'
$titleBefore = Get-GuiTitle
Say "title  : $titleBefore"
$diagLive = $titleBefore.StartsWith('DIAG')
Say "diagnostic armed: $diagLive"
$before = Save-Screenshot -Path (Join-Path $here 'shell-patch-before.png')
$beforeColors = Measure-MainRegion -Bitmap $before
$before.Dispose()
Say "main region distinct colours: $beforeColors"

Say ''
Say ('clicking the new-session button at ({0},{1})' -f $NewSessionX, $NewSessionY)
# The first run of this script reported FIXED wrongly: its own console window had
# taken the foreground, so the click landed on the console and the "after" sample
# measured the console instead of the app. Re-assert the app as the foreground
# window, and say so loudly when something else is in front.
$appWindow = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($appWindow) {
  [ShellPatchNative]::SetForegroundWindow($appWindow.MainWindowHandle) | Out-Null
  Start-Sleep -Milliseconds 800
}
$foreground = Get-GuiTitle
$appInFront = (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -eq $foreground } | Measure-Object).Count
if ($appInFront -eq 0) { Say "WARNING: something else is in front ('$foreground'); the click may miss." }
[ShellPatchNative]::SetCursorPos($NewSessionX, $NewSessionY) | Out-Null
Start-Sleep -Milliseconds 300
[ShellPatchNative]::mouse_event([ShellPatchNative]::DOWN, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Milliseconds 60
[ShellPatchNative]::mouse_event([ShellPatchNative]::UP, 0, 0, 0, [IntPtr]::Zero)
Start-Sleep -Seconds 10

Say ''
Say '--- after ---'
$titles = New-Object 'System.Collections.Generic.HashSet[string]'
for ($i = 0; $i -lt 12; $i++) {
  $t = Get-GuiTitle
  if ($t -ne '') { [void]$titles.Add($t) }
  Start-Sleep -Milliseconds 600
}
foreach ($t in $titles) { Say "title  : $t" }
$after = Save-Screenshot -Path (Join-Path $here 'shell-patch-after.png')
$afterColors = Measure-MainRegion -Bitmap $after
$after.Dispose()
Say "main region distinct colours: $afterColors"

Say ''
$blank = $afterColors -lt 20
if ($beforeColors -lt 20) {
  Say 'VERDICT: INCONCLUSIVE - the baseline itself was blank, so the click proved nothing.'
} elseif ($blank) {
  Say 'VERDICT: STILL BLANK - the patch did not stop the region from being torn down.'
} else {
  Say 'VERDICT: FIXED - creating a new session left the main region rendered.'
}
if ($diagLive) { Say 'diagnostic was armed, so any captured failure is in the titles above.' }

if ($blank -or $beforeColors -lt 20) {
  Say ''
  Say 'restarting once more so the application is left usable'
  [void](Restart-App)
}

Say 'shell-patch: done'

if ($RemoveTask -ne '') {
  try {
    Unregister-ScheduledTask -TaskName $RemoveTask -Confirm:$false -ErrorAction Stop
    Say "removed the one-shot task $RemoveTask"
  } catch {
    Say "could not remove the one-shot task $RemoveTask : $($_.Exception.Message)"
  }
}

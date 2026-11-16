# win.ps1 -- shared Win32 helpers for the mouse-hit experiments. PURE ASCII (PS 5.1 reads
# non-BOM .ps1 as ANSI/GBK and a stray Chinese comment can swallow the next line).
#
# Dot-source it:  . "$PSScriptRoot\..\lib\win.ps1"

Add-Type -Namespace EXP -Name W -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
[DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint processId);
[DllImport("user32.dll", EntryPoint="GetWindowLongPtr")] public static extern IntPtr GetWindowLongPtr(IntPtr h, int n);
[DllImport("user32.dll", EntryPoint="SetWindowLongPtr")] public static extern IntPtr SetWindowLongPtr(IntPtr h, int n, IntPtr v);
[DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr h, uint key, byte alpha, uint flags);
[DllImport("user32.dll")] public static extern bool GetLayeredWindowAttributes(IntPtr h, out uint key, out byte alpha, out uint flags);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
'@

$script:EXP_WS_EX_LAYERED = 0x00080000
$script:EXP_WS_EX_TRANSPARENT = 0x00000020
$script:EXP_GWL_EXSTYLE = -20

function Get-ExpClass([IntPtr]$h) {
  if ($h -eq [IntPtr]::Zero) { return '' }
  $sb = New-Object System.Text.StringBuilder 256
  [void][EXP.W]::GetClassName($h, $sb, 256)
  return $sb.ToString()
}

function Get-ExpTitle([IntPtr]$h) {
  if ($h -eq [IntPtr]::Zero) { return '' }
  $sb = New-Object System.Text.StringBuilder 512
  [void][EXP.W]::GetWindowText($h, $sb, 512)
  return $sb.ToString()
}

function Get-ExpRoot([IntPtr]$h) {
  if ($h -eq [IntPtr]::Zero) { return [IntPtr]::Zero }
  return [EXP.W]::GetAncestor($h, 2)  # GA_ROOT
}

function Get-ExpProcName([IntPtr]$h) {
  if ($h -eq [IntPtr]::Zero) { return '?' }
  $processId = 0
  [void][EXP.W]::GetWindowThreadProcessId($h, [ref]$processId)
  try { return (Get-Process -Id $processId -ErrorAction Stop).ProcessName } catch { return "pid:$processId" }
}

# One probe line: what would receive a click at this screen point, and is it us?
function Test-ExpPoint {
  param(
    [int]$X, [int]$Y,
    [IntPtr]$Target = [IntPtr]::Zero,   # our window handle (top-level)
    [string]$Label = ''
  )
  $p = New-Object EXP.W+POINT
  $p.X = $X; $p.Y = $Y
  $hit = [EXP.W]::WindowFromPoint($p)
  $root = Get-ExpRoot $hit
  $isUs = ($Target -ne [IntPtr]::Zero) -and (($hit -eq $Target) -or ($root -eq $Target))
  return [pscustomobject]@{
    label = $Label
    x = $X; y = $Y
    hit = ('0x' + $hit.ToString('x'))
    hitClass = (Get-ExpClass $hit)
    hitTitle = (Get-ExpTitle $hit)
    root = ('0x' + $root.ToString('x'))
    proc = (Get-ExpProcName $hit)
    isOurs = $isUs
    route = $(if ($isUs) { $(if ($hit -eq $Target) { 'ours(top)' } else { 'ours(child)' }) } else { 'OTHERS' })
  }
}

function Show-ExpPoints($points) {
  $points | Format-Table label, x, y, route, hit, hitClass, hitTitle, proc -AutoSize | Out-String -Width 200
}

# Real click at a screen point. ONLY call this after WindowFromPoint says the point belongs to
# our own window -- otherwise the click lands on the user's desktop.
function Invoke-ExpClick {
  param([int]$X, [int]$Y)
  [void][EXP.W]::SetCursorPos($X, $Y)
  Start-Sleep -Milliseconds 80
  [EXP.W]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)   # LEFTDOWN
  Start-Sleep -Milliseconds 40
  [EXP.W]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)   # LEFTUP
}

function Get-ExpShot {
  param([int]$X, [int]$Y, [int]$W, [int]$H, [string]$Out)
  Add-Type -AssemblyName System.Drawing
  $bmp = New-Object System.Drawing.Bitmap $W, $H
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($X, $Y, 0, 0, (New-Object System.Drawing.Size $W, $H))
  $full = [IO.Path]::GetFullPath($Out)
  $dir = Split-Path -Parent $full
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $bmp.Save($full, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
  return $full
}

# Sum of working set for every process whose image lives under $Prefix.
function Get-ExpMemMB([string]$Prefix) {
  $sum = 0
  foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
    try {
      if ($p.Path -and $p.Path.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) { $sum += $p.WorkingSet64 }
    } catch { }
  }
  return [math]::Round($sum / 1MB, 1)
}

function Stop-ExpProcesses([string]$Prefix) {
  foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
    try {
      if ($p.Path -and $p.Path.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
      }
    } catch { }
  }
}

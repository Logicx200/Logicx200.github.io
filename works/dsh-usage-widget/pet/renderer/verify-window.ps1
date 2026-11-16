# verify-window.ps1 -- hard evidence about a window: extended styles, click-through, topmost,
# and what WindowFromPoint actually hits at a given screen point. Pure ASCII (see run-pet.ps1).
#
#   .\verify-window.ps1 -Point 1330,700
#   .\verify-window.ps1 -Hwnd 0x9d0838 -Point 1330,700
param(
  [string]$Hwnd = '',
  [string]$Point = ''
)

Add-Type -Namespace W -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hWnd, uint gaFlags);
[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder s, int n);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
'@

# extended window style bits we care about
$WS_EX_TOPMOST     = 0x00000008
$WS_EX_TRANSPARENT = 0x00000020
$WS_EX_LAYERED     = 0x00080000
$WS_EX_TOOLWINDOW  = 0x00000080
$GWL_EXSTYLE       = -20

function Describe($h) {
  if ($h -eq [IntPtr]::Zero) { return 'NULL' }
  $len = [W.U]::GetWindowTextLength($h)
  $sb = New-Object System.Text.StringBuilder ($len + 2)
  [void][W.U]::GetWindowText($h, $sb, $sb.Capacity)
  $cb = New-Object System.Text.StringBuilder 256
  [void][W.U]::GetClassName($h, $cb, $cb.Capacity)
  $r = New-Object W.U+RECT
  [void][W.U]::GetWindowRect($h, [ref]$r)
  # NOTE: do NOT name this $pid -- $PID is a read-only automatic variable in PowerShell.
  $procId = 0
  [void][W.U]::GetWindowThreadProcessId($h, [ref]$procId)
  $ex = [int64][W.U]::GetWindowLongPtr($h, $GWL_EXSTYLE)
  $pname = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { '?' }
  [pscustomobject]@{
    hwnd        = '0x' + $h.ToString('x')
    class       = $cb.ToString()
    title       = $sb.ToString()
    rect        = "$($r.Left),$($r.Top) $($r.Right - $r.Left)x$($r.Bottom - $r.Top)"
    pid         = $procId
    process     = $pname
    exStyle     = '0x' + $ex.ToString('x8')
    topmost     = [bool]($ex -band $WS_EX_TOPMOST)
    transparent = [bool]($ex -band $WS_EX_TRANSPARENT)
    layered     = [bool]($ex -band $WS_EX_LAYERED)
    toolwindow  = [bool]($ex -band $WS_EX_TOOLWINDOW)
  }
}

if ($Hwnd) {
  $h = [IntPtr][int64]::Parse($Hwnd.Replace('0x', ''), [System.Globalization.NumberStyles]::HexNumber)
  Write-Host "--- target window ---"
  Describe $h | Format-List
}

if ($Point) {
  $xy = $Point.Split(',')
  $p = New-Object W.U+POINT
  $p.X = [int]$xy[0]; $p.Y = [int]$xy[1]
  $hit = [W.U]::WindowFromPoint($p)
  $root = [W.U]::GetAncestor($hit, 2) # GA_ROOT
  Write-Host "--- WindowFromPoint($($p.X),$($p.Y)) ---"
  Write-Host "hit (top-level of what receives the click):"
  Describe $root | Format-List
}

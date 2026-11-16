# list-windows.ps1 -- list visible top-level windows (hwnd, title, rect, process). Pure ASCII.
Add-Type -Namespace W3 -Name E -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint processId);
[DllImport("user32.dll")] public static extern IntPtr GetWindowLongPtr(IntPtr h, int n);
public delegate bool EnumProc(IntPtr h, IntPtr p);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
'@
$script:rows = New-Object System.Collections.ArrayList
$cb = [W3.E+EnumProc]{
  param($h, $p)
  if ([W3.E]::IsWindowVisible($h)) {
    $sb = New-Object System.Text.StringBuilder 512
    [void][W3.E]::GetWindowText($h, $sb, 512)
    $title = $sb.ToString()
    if ($title.Trim().Length -gt 0) {
      $cb2 = New-Object System.Text.StringBuilder 256
      [void][W3.E]::GetClassName($h, $cb2, 256)
      $r = New-Object W3.E+RECT
      [void][W3.E]::GetWindowRect($h, [ref]$r)
      $procId = 0
      [void][W3.E]::GetWindowThreadProcessId($h, [ref]$procId)
      $ex = [int64][W3.E]::GetWindowLongPtr($h, -20)
      $pname = try { (Get-Process -Id $procId -ErrorAction Stop).ProcessName } catch { '?' }
      [void]$script:rows.Add([pscustomobject]@{
        hwnd = '0x' + $h.ToString('x')
        title = $title
        cls = $cb2.ToString()
        rect = "$($r.Left),$($r.Top) $($r.Right-$r.Left)x$($r.Bottom-$r.Top)"
        pid = $procId
        proc = $pname
        topmost = [bool]($ex -band 0x8)
        layered = [bool]($ex -band 0x80000)
      })
    }
  }
  return $true
}
[void][W3.E]::EnumWindows($cb, [IntPtr]::Zero)
$script:rows | Sort-Object proc | Format-Table -AutoSize -Wrap

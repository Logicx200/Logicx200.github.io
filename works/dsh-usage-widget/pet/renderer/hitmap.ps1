# hitmap.ps1 -- which pixels of a window actually receive a mouse click right now.
#
# For every probe point it calls WindowFromPoint() and resolves the top-level ancestor: that is
# exactly the window Windows would deliver a click to. Points that resolve to the target HWND are
# '#' (the pet takes the click), anything else is '.' (the click falls through to whatever is
# below). Pure ASCII on purpose.
#
#   .\hitmap.ps1 -Hwnd 0x120ac6 -X 1150 -Y 320 -W 440 -H 540 -Step 30
param(
  [Parameter(Mandatory=$true)][string]$Hwnd,
  [Parameter(Mandatory=$true)][int]$X,
  [Parameter(Mandatory=$true)][int]$Y,
  [Parameter(Mandatory=$true)][int]$W,
  [Parameter(Mandatory=$true)][int]$H,
  [int]$Step = 30
)

Add-Type -Namespace HM -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr hWnd, uint flags);
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
'@

$target = [IntPtr][int64]::Parse($Hwnd.Replace('0x',''), [System.Globalization.NumberStyles]::HexNumber)
$hitCount = 0
$total = 0
Write-Host "target hwnd $Hwnd  window $X,$Y ${W}x${H}  step $Step  ('#' = click goes to the pet, '.' = falls through)"
for ($py = $Y; $py -lt ($Y + $H); $py += $Step) {
  $row = ''
  for ($px = $X; $px -lt ($X + $W); $px += $Step) {
    $p = New-Object HM.U+POINT
    $p.X = $px; $p.Y = $py
    $h = [HM.U]::WindowFromPoint($p)
    $root = [HM.U]::GetAncestor($h, 2)
    $total += 1
    if ($root -eq $target) { $row += '#'; $hitCount += 1 } else { $row += '.' }
  }
  Write-Host ("y={0,5}  {1}" -f $py, $row)
}
Write-Host ("clickable probe points: {0}/{1}" -f $hitCount, $total)

# c1-show.ps1 -- EXPERIMENT C1: a WPF layered window (AllowsTransparency=True) that paints one
# rectangle with alpha = 1/255, one with alpha = 0, one fully opaque. Question: does a layered
# window become hit-testable where alpha = 1/255, while alpha = 0 still passes clicks through?
# PURE ASCII.
param(
  [int]$X = 60, [int]$Y = 60, [int]$W = 420, [int]$H = 300,
  [int]$Hold = 30,
  [string]$Info = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Info) { $Info = Join-Path $here 'c1.json' }

Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml

$win = New-Object System.Windows.Window
$win.Title = 'PET-EXP-C1'
$win.WindowStyle = [System.Windows.WindowStyle]::None
$win.AllowsTransparency = $true
$win.Background = [System.Windows.Media.Brushes]::Transparent
$win.Topmost = $true
$win.ShowInTaskbar = $false
$win.Left = $X; $win.Top = $Y; $win.Width = $W; $win.Height = $H

$canvas = New-Object System.Windows.Controls.Canvas
function New-Rect([double]$left, [double]$top, [double]$w, [double]$h, $brush) {
  $r = New-Object System.Windows.Shapes.Rectangle
  $r.Width = $w; $r.Height = $h
  $r.Fill = $brush
  [System.Windows.Controls.Canvas]::SetLeft($r, $left)
  [System.Windows.Controls.Canvas]::SetTop($r, $top)
  return $r
}
# A: alpha = 1/255 (the whole point of the experiment)
$bA = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromArgb(1, 255, 255, 255))
# B: alpha = 0 (control -- must stay click-through)
$bB = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromArgb(0, 255, 255, 255))
# C: opaque (control -- a normal window would be hit here)
$bC = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromArgb(255, 60, 200, 120))

$canvas.Children.Add((New-Rect 20 20 120 120 $bA)) | Out-Null   # A  screen: X+20..X+140, Y+20..Y+140
$canvas.Children.Add((New-Rect 160 20 120 120 $bB)) | Out-Null  # B  screen: X+160..X+280
$canvas.Children.Add((New-Rect 20 160 120 120 $bC)) | Out-Null  # C  screen: X+20..X+140, Y+160..Y+280
$win.Content = $canvas

$win.Show()
[void][System.Windows.Threading.Dispatcher]::CurrentDispatcher.Invoke([action]{}, [System.Windows.Threading.DispatcherPriority]::Render)
$hwnd = (New-Object System.Windows.Interop.WindowInteropHelper($win)).Handle
[pscustomobject]@{
  hwnd = $hwnd.ToInt64(); x = $X; y = $Y; w = $W; h = $H
  allowsTransparency = $win.AllowsTransparency
  probes = [pscustomobject]@{
    alpha1 = @{ x = $X + 80;  y = $Y + 80  }   # inside A
    alpha0 = @{ x = $X + 220; y = $Y + 80  }   # inside B
    opaque = @{ x = $X + 80;  y = $Y + 220 }   # inside C
    empty  = @{ x = $X + 350; y = $Y + 260 }   # window area with no shape at all
  }
} | ConvertTo-Json -Depth 6 | Set-Content -Path $Info -Encoding UTF8

$deadline = (Get-Date).AddSeconds($Hold)
while ((Get-Date) -lt $deadline) {
  [System.Windows.Threading.Dispatcher]::CurrentDispatcher.Invoke([action]{}, [System.Windows.Threading.DispatcherPriority]::Background)
  Start-Sleep -Milliseconds 100
}
$win.Close()

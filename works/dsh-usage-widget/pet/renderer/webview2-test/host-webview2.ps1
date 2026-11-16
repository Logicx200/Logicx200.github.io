# host-webview2.ps1 -- the WebView2 host for the Live2D pet (NO Electron runtime needed).
#
# Window : WPF, WindowStyle=None + AllowsTransparency=True + Background=Transparent + Topmost
# WebView : Microsoft.Web.WebView2.Wpf.WebView2, DefaultBackgroundColor = Transparent
# Page    : the real renderer (pet/renderer/index.html), served to WebView2 through
#           SetVirtualHostNameToFolderMapping('pet.local', <pet dir>) so relative fetches work
#           without a local HTTP server and without file:// CORS problems.
# Click-through: WS_EX_TRANSPARENT added/removed on demand via SetWindowLong.
#
# Pure ASCII on purpose (Windows PowerShell 5.1 reads non-BOM .ps1 as ANSI and can swallow lines).
#
#   .\host-webview2.ps1 -X 1150 -Y 320 -W 440 -H 540 -ClickThrough 1 -Hold 25 -Info out.json
param(
  [int]$X = -1, [int]$Y = -1, [int]$W = 440, [int]$H = 540,
  [int]$ClickThrough = 1,
  [int]$Topmost = 1,
  [int]$Hold = 25,
  [string]$Info = '',
  [string]$Q = '',
  [string]$Page = 'renderer/index.html',
  [string]$Shot = ''
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$petRoot = [IO.Path]::GetFullPath((Join-Path $here '..\..'))
# Default outputs next to this script: do not depend on argv, which is the one thing that can
# get mangled for paths with non-ASCII characters.
if (-not $Info) { $Info = Join-Path $here 'wv2-info.json' }
if (-not $Shot) { $Shot = Join-Path $here 'wv2-proof.png' }
$log = Join-Path $here 'host-webview2.log'
function L($m) { Add-Content -Path $log -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $m) -Encoding UTF8 }
Set-Content -Path $log -Value '' -Encoding UTF8

$WS_EX_TRANSPARENT = 0x00000020
$GWL_EXSTYLE = -20

try {
  L "start; petRoot=$petRoot ps=$($PSVersionTable.PSVersion) apartment=$([System.Threading.Thread]::CurrentThread.GetApartmentState())"

  Add-Type -Namespace WV2 -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool SetDllDirectory(string path);
[DllImport("user32.dll", EntryPoint="GetWindowLongPtr")] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
[DllImport("user32.dll", EntryPoint="SetWindowLongPtr")] public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
'@
  [void][WV2.Native]::SetDllDirectory($here)
  $env:PATH = $here + ';' + $env:PATH

  Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml
  Add-Type -AssemblyName System.Drawing
  Add-Type -AssemblyName System.Windows.Forms
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $here 'Microsoft.Web.WebView2.Core.dll'))
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $here 'Microsoft.Web.WebView2.Wpf.dll'))
  L 'webview2 assemblies loaded'

  $wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  if ($X -lt 0) { $X = $wa.Right - $W - 8 }
  if ($Y -lt 0) { $Y = $wa.Bottom - $H - 8 }

  $win = New-Object System.Windows.Window
  $win.WindowStyle = [System.Windows.WindowStyle]::None
  $win.AllowsTransparency = $true
  $win.Background = [System.Windows.Media.Brushes]::Transparent
  $win.Topmost = [bool]$Topmost
  $win.ShowInTaskbar = $false
  $win.ResizeMode = [System.Windows.ResizeMode]::NoResize
  $win.Left = $X; $win.Top = $Y; $win.Width = $W; $win.Height = $H

  $grid = New-Object System.Windows.Controls.Grid
  $wv = New-Object Microsoft.Web.WebView2.Wpf.WebView2
  $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
  [void]$grid.Children.Add($wv)
  $win.Content = $grid
  $win.Show()
  $hwnd = (New-Object System.Windows.Interop.WindowInteropHelper($win)).Handle
  L "window shown hwnd=0x$($hwnd.ToString('x')) at $X,$Y ${W}x${H} topmost=$($win.Topmost)"

  function Set-ClickThrough([bool]$on) {
    $ex = [int64][WV2.Native]::GetWindowLongPtr($hwnd, $GWL_EXSTYLE)
    if ($on) { $ex = $ex -bor $WS_EX_TRANSPARENT } else { $ex = $ex -band (-bnot $WS_EX_TRANSPARENT) }
    [void][WV2.Native]::SetWindowLongPtr($hwnd, $GWL_EXSTYLE, [IntPtr]$ex)
    return $ex
  }

  $script:phase = 0
  $script:ticks = 0
  $script:task = $null
  $script:readyAt = 0
  $script:alpha = $null
  $timer = New-Object System.Windows.Threading.DispatcherTimer
  $timer.Interval = [TimeSpan]::FromMilliseconds(300)
  $timer.Add_Tick({
    if ($script:phase -eq 0) {
      if ($wv.IsLoaded) { $script:task = $wv.EnsureCoreWebView2Async($null); $script:phase = 1; L 'EnsureCoreWebView2Async called' }
      return
    }
    if ($script:phase -eq 1) {
      if (-not $script:task.IsCompleted) { return }
      if ($script:task.IsFaulted) { L ('FAULT: ' + $script:task.Exception.ToString()); $script:phase = 99; return }
      $core = $wv.CoreWebView2
      L "core ready runtime=$($core.Environment.BrowserVersionString)"
      $core.SetVirtualHostNameToFolderMapping('pet.local', $petRoot, [Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
      $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
      $url = "https://pet.local/$Page"
      if ($Q) { $url += "?$Q" }
      L "navigating to $url"
      $wv.Source = New-Object System.Uri $url
      $script:phase = 2
      return
    }
    if ($script:phase -eq 2) {
      # give the model time to load (moc3 + 2 textures + physics)
      $script:ticks += 1
      if ($script:ticks -lt 22) { return }
      $script:alphaTask = $wv.CoreWebView2.ExecuteScriptAsync('JSON.stringify({ready:!!window.__PET_READY__,alpha:(window.PetAPI&&PetAPI.alphaProbe)?PetAPI.alphaProbe():null,state:(window.PetAPI&&PetAPI.getState)?PetAPI.getState():null})')
      $script:alpha = $null
      $script:phase = 3
      $script:ticks = 0
      return
    }
    if ($script:phase -eq 3) {
      $script:ticks += 1
      if ($script:alphaTask -ne $null -and $script:alphaTask.IsCompleted) { $script:alpha = $script:alphaTask.Result }
      if ($script:alpha -eq $null -and $script:ticks -lt 20) { return }
      if ($ClickThrough) { [void](Set-ClickThrough $true) }
      $ct = [bool](([int64][WV2.Native]::GetWindowLongPtr($hwnd, $GWL_EXSTYLE)) -band $WS_EX_TRANSPARENT)
      $infoObj = [ordered]@{
        ok = $true
        host = 'WPF + WebView2 (Microsoft.Web.WebView2.Wpf, SDK 1.0.3179.45)'
        hwnd = '0x' + $hwnd.ToString('x')
        bounds = @{ x = $X; y = $Y; width = $W; height = $H }
        topmost = $win.Topmost
        clickThrough = $ct
        allowsTransparency = $win.AllowsTransparency
        windowBackground = $win.Background.ToString()
        webviewDefaultBackground = $wv.DefaultBackgroundColor.ToString()
        runtime = $wv.CoreWebView2.Environment.BrowserVersionString
        url = $wv.Source.ToString()
        page = $script:alpha
      }
      $jsonText = ($infoObj | ConvertTo-Json -Depth 6)
      if ($Info) { Set-Content -Path $Info -Value $jsonText -Encoding UTF8 }
      L ('INFO ' + $jsonText)
      if ($Shot) {
        $bmp = New-Object System.Drawing.Bitmap ($W + 160), ($H + 160)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen([Math]::Max(0, $X - 80), [Math]::Max(0, $Y - 80), 0, 0, (New-Object System.Drawing.Size (($W + 160), ($H + 160))))
        $bmp.Save($Shot, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        L "screenshot saved $Shot"
      }
      $script:phase = 4
      $script:deadline = (Get-Date).AddSeconds($Hold)
      return
    }
    if ($script:phase -eq 4) {
      if ((Get-Date) -lt $script:deadline) { return }
      $timer.Stop()
      $win.Close()
      [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
    }
  })
  $timer.Start()
  [System.Windows.Threading.Dispatcher]::Run()
  L 'DONE'
} catch {
  L ('EXCEPTION: ' + $_.Exception.ToString())
  L ('at: ' + $_.InvocationInfo.PositionMessage)
}

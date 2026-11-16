# wpf-transparent.ps1 -- ROUTE 1: WPF window with AllowsTransparency=True hosting WebView2.
#
# WebView2 .NET Framework 4.6.2 SDK 1.0.3179.45 (copied next to this script) + matching native
# WebView2Loader.dll. Installed WebView2 runtime: 154.0.4258.37.
# Page = fully transparent background + one opaque red circle + one green ring.
# That isolates "can WebView2 be transparent here" from any Live2D question.
#
# NOTE: WebView2's WPF control refuses EnsureCoreWebView2Async() until a Dispatcher loop is
# running, so this is written as a small state machine driven by a DispatcherTimer, and the
# blocking [Dispatcher]::Run() is entered last. Pure ASCII on purpose.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here 'wpf-transparent.log'
function L($m) { Add-Content -Path $log -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $m) -Encoding UTF8 }
Set-Content -Path $log -Value '' -Encoding UTF8

try {
  L "start; ps=$($PSVersionTable.PSVersion) apartment=$([System.Threading.Thread]::CurrentThread.GetApartmentState())"

  Add-Type -Namespace WV -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool SetDllDirectory(string path);
'@
  [void][WV.Native]::SetDllDirectory($here)
  $env:PATH = $here + ';' + $env:PATH

  Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $here 'Microsoft.Web.WebView2.Core.dll'))
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $here 'Microsoft.Web.WebView2.Wpf.dll'))
  Add-Type -AssemblyName System.Drawing
  L "webview2 assemblies loaded"

  $html = @'
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;width:100%;height:100%;background:transparent}
#dot{width:170px;height:170px;border-radius:50%;background:#ff3b30;margin:60px 0 0 75px}
#ring{width:56px;height:56px;border:8px solid #34c759;border-radius:50%;margin:10px 0 0 75px}
</style></head><body><div id="dot"></div><div id="ring"></div></body></html>
'@

  $win = New-Object System.Windows.Window
  $win.WindowStyle = [System.Windows.WindowStyle]::None
  $win.AllowsTransparency = $true
  $win.Background = [System.Windows.Media.Brushes]::Transparent
  $win.Topmost = $true
  $win.ShowInTaskbar = $false
  $win.Width = 320; $win.Height = 320
  $win.Left = 40; $win.Top = 40

  $grid = New-Object System.Windows.Controls.Grid
  $wv = New-Object Microsoft.Web.WebView2.Wpf.WebView2
  $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
  [void]$grid.Children.Add($wv)
  $win.Content = $grid
  $win.Show()
  L "wpf window shown; AllowsTransparency=$($win.AllowsTransparency) bg=$($win.Background) DefaultBackgroundColor=$($wv.DefaultBackgroundColor)"

  $script:waited = 0
  $script:ticks = 0
  $script:started = $false
  $script:task = $null
  $timer = New-Object System.Windows.Threading.DispatcherTimer
  $timer.Interval = [TimeSpan]::FromMilliseconds(250)
  $timer.Add_Tick({
    $script:waited += 250
    # EnsureCoreWebView2Async may only be called while the Dispatcher loop is running,
    # so it has to be kicked off from inside a timer tick.
    if (-not $script:started) {
      if ($wv.IsLoaded) {
        L "control loaded; calling EnsureCoreWebView2Async"
        $script:task = $wv.EnsureCoreWebView2Async($null)
        $script:started = $true
      } elseif ($script:waited -ge 20000) {
        L "TIMEOUT: control never loaded"
        $win.Close(); [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
      }
      return
    }
    if (-not $script:task.IsCompleted) {
      if ($script:waited -ge 30000) {
        L "TIMEOUT: EnsureCoreWebView2Async never completed"
        $win.Close(); [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
      }
      return
    }
    if ($script:task.IsFaulted) {
      L ("FAULT: " + $script:task.Exception.ToString())
      $timer.Stop(); $win.Close()
      [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
      return
    }
    if ($null -eq $wv.CoreWebView2) { return }
    if ($script:ticks -eq 0) {
      L "CoreWebView2 ready after ${script:waited}ms; runtime=$($wv.CoreWebView2.Environment.BrowserVersionString)"
      $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
      $wv.CoreWebView2.NavigateToString($html)
      L "NavigateToString called; DefaultBackgroundColor=$($wv.DefaultBackgroundColor)"
    }
    $script:ticks += 1
    L "tick $($script:ticks) url=$($wv.CoreWebView2.Source)"
    if ($script:ticks -ge 14) {
      $bmp = New-Object System.Drawing.Bitmap 420, 420
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen(0, 0, 0, 0, (New-Object System.Drawing.Size 420, 420))
      $png = Join-Path $here 'wpf-transparent.png'
      $bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
      $g.Dispose(); $bmp.Dispose()
      L "screenshot saved: $png"
      $timer.Stop()
      $win.Close()
      [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
    }
  })
  $timer.Start()

  L 'entering Dispatcher.Run()'

  [System.Windows.Threading.Dispatcher]::Run()
  L 'dispatcher loop exited; DONE'
} catch {
  L ("EXCEPTION: " + $_.Exception.ToString())
  L ("at: " + $_.InvocationInfo.PositionMessage)
} finally {
  Get-Content $log -Encoding UTF8 | Write-Host
}

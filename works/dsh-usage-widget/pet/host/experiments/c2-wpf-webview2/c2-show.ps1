# c2-show.ps1 -- EXPERIMENT C2: WPF (AllowsTransparency) + WebView2, where the WPF layer paints an
# alpha=1/255 rectangle over the LEFT half only, and the page draws one OPAQUE red circle there.
#
# Three questions:
#   P1 over the page's opaque circle   -> does the click reach the WebView2 CHILD (page) or the WPF parent?
#   P2 over the alpha=1 layer only     -> region hit: does the WPF parent take it?
#   P3 over nothing (right half)       -> must still fall through to the desktop
# A page counter (window.__clicks) is polled and written to the info json, so a real click can be
# verified from the page's point of view. PURE ASCII.
param(
  [int]$X = 60, [int]$Y = 60, [int]$W = 480, [int]$H = 320,
  [int]$Hold = 40,
  [string]$Info = ''
)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$lib = Join-Path $here '..\lib\webview2'
if (-not $Info) { $Info = Join-Path $here 'c2.json' }
$log = Join-Path $here 'c2-show.log'
function L($m) { Add-Content -Path $log -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $m) -Encoding UTF8 }
Set-Content -Path $log -Value '' -Encoding UTF8

try {
  Add-Type -Namespace EXP2 -Name N -MemberDefinition @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode)] public static extern bool SetDllDirectory(string path);
'@
  [void][EXP2.N]::SetDllDirectory($lib)
  $env:PATH = $lib + ';' + $env:PATH
  Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $lib 'Microsoft.Web.WebView2.Core.dll'))
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $lib 'Microsoft.Web.WebView2.Wpf.dll'))
  L 'assemblies ok'

  # Page: transparent everywhere, ONE opaque red circle on the left half.
  # Clicks are reported back through window.chrome.webview.postMessage, so the HOST records them
  # event-driven (no polling of ExecuteScriptAsync, which silently failed once).
  $html = @'
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;width:100%;height:100%;background:transparent;overflow:hidden}
#dot{position:absolute;left:30px;top:70px;width:180px;height:180px;border-radius:50%;background:#ff2d20}
#n{position:absolute;left:250px;top:20px;color:#0f0;font:16px Consolas;background:#000a;padding:4px}
</style></head><body>
<div id="dot"></div><div id="n">page clicks: <span id="c">0</span></div>
<script>
window.__clicks = 0
function post(kind, e){
  var msg = { kind: kind, x: e.clientX, y: e.clientY, n: window.__clicks, t: Date.now() }
  try { window.chrome.webview.postMessage(JSON.stringify(msg)) } catch (err) { }
}
function bump(e){
  window.__clicks++
  document.getElementById('c').textContent = window.__clicks
  post('down', e)
}
document.addEventListener('mousedown', bump, true)
document.addEventListener('pointerdown', bump, true)
document.addEventListener('mousemove', function(e){
  if (!window.__mv || Date.now() - window.__mv > 400) { window.__mv = Date.now(); post('move', e) }
}, true)
setTimeout(function(){ try { window.chrome.webview.postMessage(JSON.stringify({kind:'ready',n:0,t:Date.now()})) } catch(e){} }, 100)
</script></body></html>
'@

  $win = New-Object System.Windows.Window
  $win.Title = 'PET-EXP-C2'
  $win.WindowStyle = [System.Windows.WindowStyle]::None
  $win.AllowsTransparency = $true
  $win.Background = [System.Windows.Media.Brushes]::Transparent
  $win.Topmost = $true
  $win.ShowInTaskbar = $false
  $win.Left = $X; $win.Top = $Y; $win.Width = $W; $win.Height = $H

  $grid = New-Object System.Windows.Controls.Grid
  # bottom layer: the alpha=1/255 "silhouette" over the LEFT HALF only
  $canvas = New-Object System.Windows.Controls.Canvas
  $rect = New-Object System.Windows.Shapes.Rectangle
  $rect.Width = $W / 2; $rect.Height = $H
  $rect.Fill = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromArgb(1, 0, 0, 0))
  [System.Windows.Controls.Canvas]::SetLeft($rect, 0)
  [System.Windows.Controls.Canvas]::SetTop($rect, 0)
  $canvas.Children.Add($rect) | Out-Null
  $grid.Children.Add($canvas) | Out-Null
  # top layer: WebView2 filling the window
  $wv = New-Object Microsoft.Web.WebView2.Wpf.WebView2
  $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
  $grid.Children.Add($wv) | Out-Null
  $win.Content = $grid
  $win.Show()
  $hwnd = (New-Object System.Windows.Interop.WindowInteropHelper($win)).Handle
  L ("window hwnd=0x{0:x} at {1},{2} {3}x{4}" -f $hwnd.ToInt64(), $X, $Y, $W, $H)

  $script:phase = 0
  $script:task = $null
  $script:clicks = -1
  $script:msgs = New-Object System.Collections.ArrayList
  $script:lastMsg = ''
  $script:deadline = (Get-Date).AddSeconds($Hold)
  $script:write = {
    $json = [pscustomobject]@{
      hwnd = $hwnd.ToInt64(); x = $X; y = $Y; w = $W; h = $H
      allowsTransparency = $win.AllowsTransparency
      pageClicks = $script:clicks
      lastMessage = $script:lastMsg
      messageCount = $script:msgs.Count
      probes = [pscustomobject]@{
        p1_page_opaque_and_alpha1 = @{ x = $X + 120; y = $Y + 160 }
        p2_alpha1_only            = @{ x = $X + 20;  y = $Y + 20  }
        p3_nothing                = @{ x = $X + 400; y = $Y + 160 }
      }
    } | ConvertTo-Json -Depth 6
    # write via a temp file + move: the reader polls this file, and a direct overwrite makes
    # Get-Content fail with "file is in use by another process".
    Set-Content -Path ($Info + '.tmp') -Value $json -Encoding UTF8
    Move-Item -Path ($Info + '.tmp') -Destination $Info -Force
  }

  $timer = New-Object System.Windows.Threading.DispatcherTimer
  $timer.Interval = [TimeSpan]::FromMilliseconds(400)
  $timer.Add_Tick({
    if ($script:phase -eq 0) {
      if ($wv.IsLoaded) { $script:task = $wv.EnsureCoreWebView2Async($null); $script:phase = 1; L 'EnsureCoreWebView2Async called' }
      return
    }
    if ($script:phase -eq 1) {
      if (-not $script:task.IsCompleted) { return }
      if ($script:task.IsFaulted) { L ('FAULT ' + $script:task.Exception.ToString()); $script:phase = 9; return }
      $core = $wv.CoreWebView2
      $core.add_WebMessageReceived({
        # NOTE: do NOT name the second parameter $args -- that collides with PowerShell's automatic
        # $args variable, so the property lookup silently goes to the Object[] instead.
        param($sender, $ev)
        $raw = ''
        try { $raw = [string]$ev.WebMessageAsJson } catch { L ('WebMessageAsJson threw: ' + $_.Exception.Message) }
        $script:lastMsg = $raw
        [void]$script:msgs.Add($raw)
        L ('MSG len=' + $raw.Length + ' body=' + $raw)
        try {
          # WebMessageAsJson wraps a string message in a JSON string literal, so one ConvertFrom-Json
          # yields a .NET string and the object needs a second pass.
          $o = $raw | ConvertFrom-Json
          if ($o -is [string]) { $o = $o | ConvertFrom-Json }
          if ($o.kind -eq 'down') { $script:clicks = [int]$o.n }
        } catch { L ('parse failed: ' + $_.Exception.Message) }
      })
      $core.NavigateToString($html)
      L 'navigated'
      $script:phase = 2
      $script:ticks = 0
      return
    }
    if ($script:phase -eq 2) {
      $script:ticks++
      if ($script:ticks -lt 8) { return }
      $script:phase = 3
      return
    }
    if ($script:phase -eq 3) {
      & $script:write
      if ((Get-Date) -ge $script:deadline) {
        $timer.Stop(); $wv.Dispose(); $win.Close()
        [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
      }
    }
  })
  $timer.Start()
  [System.Windows.Threading.Dispatcher]::Run()
  L 'done'
} catch {
  L ('EXCEPTION ' + $_.Exception.ToString())
}

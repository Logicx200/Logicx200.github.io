# host.ps1 -- the Live2D pet's window: WPF + WebView2 (no Electron runtime needed).
#
# Started by the panel (ui\widget.ps1), one instance per panel, for the whole
# life of the panel:
#
#   powershell.exe -NoProfile -File "<...>\pet\host\host.ps1" ^
#       -X 1562 -Y 674 -W 340 -H 340 -ParentPid <panel pid> ^
#       -StopFile "<tmp>\dsh-usage-widget-pet.stop" -AnchorBr -Fill 0.735
#
# The recipe is the one proved by pet\renderer\webview2-test\host-webview2.ps1
# and written up in pet\renderer\README.md:
#
#   Window    : WindowStyle=None + AllowsTransparency=True + Background=Transparent
#               + Topmost=True + ShowInTaskbar=False + ResizeMode=NoResize
#   WebView   : Microsoft.Web.WebView2.Wpf.WebView2, DefaultBackgroundColor=Transparent,
#               SetVirtualHostNameToFolderMapping('pet.local', <pet dir>) and
#               Source=https://pet.local/renderer/index.html so the page's relative
#               fetches work without a local HTTP server and without file:// CORS.
#   Native    : WebView2Loader.dll must be findable -> SetDllDirectory(<sdk dir>).
#   Order     : WebView2 refuses EnsureCoreWebView2Async before the dispatcher
#               loop runs, so everything happens in dispatcher-timer phases and
#               the script only blocks at the very end, in [Dispatcher]::Run().
#
# This window is **click-through on purpose** (a per-alpha hit-tested layered
# window whose WPF drawing surface is empty), so the pet never blocks a desktop
# that so the guarantee does not depend on how the layered hit-test falls out.
#
# Lifecycle: the host exits when the parent panel dies (ParentPid disappears),
# when the panel creates the StopFile, when -Hold seconds elapse (0 = never), or
# when its window is closed. It never writes anywhere except its own log and info
# files. All output files are next to this script.
#
# It also MEASURES the character for the panel: every 1.5 s it asks the page for
# PetAPI.modelMetrics() (the character's box, measured on the page with PixiJS
# bounds plus an alpha scan of the rendered frame, and the label's rect), converts
# that to screen px with the window's real rect, and writes pet\host\model.json.
# ui\widget.ps1 reads that file and aligns its right edge with the character's
# right edge, so the panel follows the pet and not the other way round.
#
# Pure ASCII on purpose: Windows PowerShell 5.1 reads a BOM-less .ps1 as GBK and a
# non-ASCII comment can swallow the following line (pet\renderer\README.md 4.2).
param(
  [int]$X = -1,
  [int]$Y = -1,
  [int]$W = 340,
  [int]$H = 340,
  # The panel that owns this process; 0 disables the check.
  [int]$ParentPid = 0,
  # Touch this file to ask the host to exit cleanly (the panel does exactly that).
  [string]$StopFile = '',
  # Page inside the pet folder, and an extra query string for it.
  [string]$Page = 'renderer/index.html',
  [string]$Q = '',
  # Anchor the model box to the viewport's bottom-right (see pet\renderer\pet-app.js
  # ?anchor=br) and keep this fraction of the fitted size.  The window is pinned to
  # the work area's bottom-right corner by the panel; the panel then aligns its own
  # right edge with this character's measured right edge.
  [switch]$AnchorBr,
  [double]$Fill = 0.735,
  # Move the model this many page px to the LEFT inside the window.  Its animated
  # geometry (the whale tail, physics-driven) reaches ~8 page px beyond its own
  # canvas box, and with -AnchorBr that box ends exactly at the window's right
  # edge, so those pixels used to be cut off flat.  16 px leaves room for the
  # tail to swing without touching the window edge; the measured model box moves
  # left with it and the panel follows the measurement.
  [double]$ModelShiftX = 16,
  # Move the model this many page px DOWN inside the window, into the ~33 px of
  # transparent space the model leaves under the character.  The pair then sits
  # closer to the taskbar without the character being cut by the window's bottom
  # edge (the silhouette must stay above it), and the panel's bottom follows.
  [double]$ModelShiftY = 0,
  [int]$ClickThrough = 1,
  # Seconds to run; 0 = until the parent dies / the stop file appears / closed.
  [int]$Hold = 0,
  # Outputs (defaults are next to this script).
  [string]$Info = '',
  [string]$Log = '',
  # Where the character's measured box is published for the panel (ui\widget.ps1).
  [string]$Metrics = ''
)

$ErrorActionPreference = 'Continue'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$petRoot = [IO.Path]::GetFullPath((Join-Path $here '..'))
if (-not $Log) { $Log = Join-Path $here 'host.log' }
if (-not $Info) { $Info = Join-Path $here 'pet-host.json' }
if (-not $Metrics) { $Metrics = Join-Path $here 'model.json' }
# Where the page's own reports (e.g. the ?selftest=1 expression run) are written.
$script:pageMessagePath = Join-Path $here 'page-message.json'
# Development capture channel: write a JSON payload here (or delete it) and the
# host pushes it into the page as `window.postMessage({type:'pet-force',payload})`.
$script:forceStatePath = Join-Path $here 'force-state.json'
$script:forceSeen = '__init__'
$script:forceTick = 0
# Development watch channel: write {ms,params} here and the page samples those
# parameters in-frame and reports back (pet\host\page-message.json).
$script:watchPath = Join-Path $here 'watch.json'
$script:watchSeen = '__init__'
# Drag offset (from the "home" corner) that the panel reads so a dragged pet - and the
# panel with it - stays where the user put it.
$script:log = $Log
function L($m) {
  try { Add-Content -Path $script:log -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $m) -Encoding UTF8 } catch { }
}
try { Set-Content -Path $Log -Value '' -Encoding UTF8 } catch { }

$script:exiting = $false
$script:phase = 0
$script:ticks = 0
$script:maintainTick = 0
$script:deadline = $null
$script:metricsTask = $null
$script:metricsLog = 0
$script:metricsStable = ''
$script:metricsWrittenAt = [datetime]::MinValue

$WS_EX_TRANSPARENT = 0x00000020
$GWL_EXSTYLE = -20
$HWND_TOPMOST = [IntPtr](-1)
$SWP_NOSIZE = 0x0001
$SWP_NOMOVE = 0x0002
$SWP_NOACTIVATE = 0x0010

# --------------------------------------------------------------------------
# 0. find the WebView2 SDK, load it
# --------------------------------------------------------------------------
# The SDK (net462, 1.0.3179.45) comes from C:\Program Files\SakuraFrpLauncher\; the
# installed runtime is 154.0.4258.37 (SDK <= runtime).
#
# WHY THE MANAGED ASSEMBLIES ARE LOADED FROM BYTES (2026-10-06/07 outage, task-16/17):
# Assembly.LoadFrom threw System.NotSupportedException 0x80131515 ("attempt to load an
# assembly from a network location") for Microsoft.Web.WebView2.Core.dll - and it kept
# doing so after the project had been moved to the pure-ASCII F:\dsh-usage-widget.  The
# measurements that finally explained it:
#   * the DLL has NO Zone.Identifier stream, F: is a local Fixed volume, the AppDomain is
#     fully trusted and no loadFromRemoteSources policy is set;
#   * LoadFrom failed for the project copy, for a copy under %LOCALAPPDATA%, and for the
#     ASCII copy alike -> not a path property;
#   * a brand-new file created inside the project folder was rejected by PowerShell too,
#     while the same content in F:\<fresh folder> ran, and Unblock-File did not help;
#   => the *file and directory objects* carried a leftover mark from the untrusted parent
#      folder (it travels with a move/rename, which is why moving the project did NOT fix
#      anything).  Rewriting every .ps1/DLL as a fresh file object cleared it: LoadFrom and
#      unsigned script execution both work now.
# Assembly.Load(byte[]) is kept because it is immune to that whole class of mark and costs
# nothing; LoadFrom stays as a fallback and the log says which one was used.
# The native WebView2Loader.dll is not a managed assembly and is found via SetDllDirectory.
# SDK location is configurable: -SdkDir, then $env:DSH_PET_WEBVIEW2_SDK, then the SDK that
# ships in this repo (..\renderer\webview2-test), then %LOCALAPPDATA%\dsh-usage-widget\
# webview2-sdk, then beside this script.
$sdkCandidates = @()
if ($SdkDir) { $sdkCandidates += $SdkDir }
if ($env:DSH_PET_WEBVIEW2_SDK) { $sdkCandidates += $env:DSH_PET_WEBVIEW2_SDK }
$sdkCandidates += $here
$sdkCandidates += [IO.Path]::GetFullPath((Join-Path $here '..\renderer\webview2-test'))
if ($env:LOCALAPPDATA) { $sdkCandidates += (Join-Path $env:LOCALAPPDATA 'dsh-usage-widget\webview2-sdk') }
$sdk = $null
foreach ($candidate in $sdkCandidates) {
  if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
  if (Test-Path -LiteralPath (Join-Path $candidate 'Microsoft.Web.WebView2.Wpf.dll')) { $sdk = $candidate; break }
  L ("sdk candidate rejected (no Wpf dll): " + $candidate)
}
if ($null -eq $sdk) {
  L 'FATAL no Microsoft.Web.WebView2.Wpf.dll in any candidate dir; run pet\host\deploy-sdk.ps1'
  exit 2
}
L "host start; sdk=$sdk petRoot=$petRoot ps=$($PSVersionTable.PSVersion) apartment=$([System.Threading.Thread]::CurrentThread.GetApartmentState())"

# Load one SDK assembly from bytes; LoadFrom only as a last resort (and say so in the log).
function Load-PetSdkAssembly([string]$dir, [string]$name) {
  $p = Join-Path $dir $name
  if (-not (Test-Path -LiteralPath $p)) { L ("sdk: " + $name + " not present in " + $dir); return $true }
  try {
    [void][System.Reflection.Assembly]::Load([IO.File]::ReadAllBytes($p))
    L ("sdk: loaded " + $name + " from bytes (" + $dir + ")")
    return $true
  } catch {
    L ("sdk: byte-load failed for " + $name + ": " + $_.Exception.Message)
  }
  try {
    [void][System.Reflection.Assembly]::LoadFrom($p)
    L ("sdk: LoadFrom fallback ok for " + $name)
    return $true
  } catch {
    L ("sdk: FATAL cannot load " + $name + " from " + $dir + ": " + $_.Exception.Message)
    return $false
  }
}

try {
  Add-Type -Namespace PetHost -Name Native -MemberDefinition @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool SetDllDirectory(string path);
[DllImport("user32.dll", EntryPoint="GetWindowLongPtr")] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
[DllImport("user32.dll", EntryPoint="SetWindowLongPtr")] public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
[DllImport("user32.dll", SetLastError=true)] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
[DllImport("user32.dll", SetLastError=true)] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
'@
  # the NATIVE loader must be findable by name when Core.dll P/Invokes it
  [void][PetHost.Native]::SetDllDirectory($sdk)
  $env:PATH = $sdk + ';' + $env:PATH

  Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Xaml
  Add-Type -AssemblyName System.Drawing
  Add-Type -AssemblyName System.Windows.Forms
  $ok = $true
  # Core first: the Wpf assembly references it by name and must resolve to this instance.
  $ok = (Load-PetSdkAssembly $sdk 'Microsoft.Web.WebView2.Core.dll') -and $ok
  $ok = (Load-PetSdkAssembly $sdk 'Microsoft.Web.WebView2.Wpf.dll') -and $ok
  $ok = (Load-PetSdkAssembly $sdk 'Microsoft.Web.WebView2.WinForms.dll') -and $ok
  if (-not $ok) { L 'FATAL the WebView2 SDK could not be loaded'; exit 3 }
  if (-not (Test-Path -LiteralPath (Join-Path $sdk 'WebView2Loader.dll'))) {
    L ('WARN WebView2Loader.dll missing in ' + $sdk + ' - the native loader may not resolve')
  }
  L 'webview2 assemblies loaded'
} catch {
  L ('FATAL loading assemblies: ' + $_.Exception.ToString())
  exit 3
}

$wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
if ($X -lt 0) { $X = $wa.Right - $W - 8 }
if ($Y -lt 0) { $Y = $wa.Bottom - $H - 8 }

# The page's own query: ?anchor=br keeps the character in the window's
# bottom-right, which is what leaves the panel's text visible.
$query = $Q
if ($AnchorBr) {
  if ($Fill -le 0 -or $Fill -gt 1) { $Fill = 0.735 }
  $anchor = 'anchor=br&fill=' + $Fill.ToString([System.Globalization.CultureInfo]::InvariantCulture)
  if ($ModelShiftX -gt 0 -and $W -gt 0) {
    # page px -> the page's viewport fraction (CSS px == the window's DIPs here)
    $dx = -$ModelShiftX / [double]$W
    $anchor += '&dx=' + $dx.ToString([System.Globalization.CultureInfo]::InvariantCulture)
  }
  if ($ModelShiftY -gt 0 -and $H -gt 0) {
    $dy = $ModelShiftY / [double]$H
    $anchor += '&dy=' + $dy.ToString([System.Globalization.CultureInfo]::InvariantCulture)
  }
  if ($query) { $query = $anchor + '&' + $query } else { $query = $anchor }
}

$script:win = $null
$script:wv = $null
$script:hwnd = [IntPtr]::Zero
$script:envTask = $null
$script:coreTask = $null
$script:probeTask = $null
$script:probe = $null
$script:timer = $null

function Exit-Host([string]$why) {
  if ($script:exiting) { return }
  $script:exiting = $true
  L ('exit: ' + $why)
  try { if ($script:timer) { $script:timer.Stop() } } catch { }
  try { if ($script:win) { $script:win.Close() } } catch { }
  try { [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown() } catch { }
}

try {
  $win = New-Object System.Windows.Window
  $win.WindowStyle = [System.Windows.WindowStyle]::None
  $win.AllowsTransparency = $true
  $win.Background = [System.Windows.Media.Brushes]::Transparent
  $win.Topmost = $true
  $win.ShowInTaskbar = $false
  $win.ResizeMode = [System.Windows.ResizeMode]::NoResize
  $win.ShowActivated = $false
  $win.Title = 'DSH pet'
  $win.Left = $X
  $win.Top = $Y
  $win.Width = $W
  $win.Height = $H
  $script:win = $win

  $grid = New-Object System.Windows.Controls.Grid
  $wv = New-Object Microsoft.Web.WebView2.Wpf.WebView2
  $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
  [void]$grid.Children.Add($wv)
  $win.Content = $grid
  $script:wv = $wv

  $win.Show()
  $script:hwnd = (New-Object System.Windows.Interop.WindowInteropHelper($win)).Handle
  L ("window shown hwnd=0x{0} at {1},{2} {3}x{4}" -f $script:hwnd.ToString('x'), $X, $Y, $W, $H)
} catch {
  L ('FATAL creating the window: ' + $_.Exception.ToString())
  exit 4
}

# One WebView2 user-data folder of our own, so this app never shares a profile
# (or a lock) with any other WebView2 host on the machine.
$udd = Join-Path $env:LOCALAPPDATA 'dsh-usage-widget\webview2'

# --------------------------------------------------------------------------
# 4b. the CHARACTER's measured box, published for the panel
# --------------------------------------------------------------------------
# The page measures the character (PixiJS getBounds() for the canvas box plus an
# alpha scan of the model rendered offscreen for the real silhouette) and exposes
# it as PetAPI.modelMetrics() in page CSS px.  This host converts that box to
# screen coordinates using the window's real rect - the panel moves the window,
# so the WPF Left/Top properties are not trusted - and writes it next to this
# script, where ui\widget.ps1 reads it to align its own right edge with the
# character's right edge.  No cycle: the pet window is anchored to the work area,
# the panel follows the measurement, and the measurement never depends on the panel.
function Request-Metrics {
  if ($null -ne $script:metricsTask -and -not $script:metricsTask.IsCompleted) { return }
  try {
    $script:metricsTask = $script:wv.CoreWebView2.ExecuteScriptAsync('JSON.stringify((window.PetAPI&&PetAPI.modelMetrics)?PetAPI.modelMetrics():null)')
  } catch {
    $script:metricsTask = $null
    L ('metrics probe failed: ' + $_.Exception.Message)
  }
}

function Collect-Metrics {
  $task = $script:metricsTask
  $script:metricsTask = $null
  if ($null -eq $task) { return }
  $raw = $null
  try { $raw = $task.Result } catch { return }
  # NOTE: this variable must NOT be called $metrics - PowerShell variable names are
  # case-insensitive, so it would silently shadow the $Metrics parameter above and
  # turn `$Metrics + '.tmp'` into "add a string to a PSObject".
  $pageMetrics = $null
  try {
    # ExecuteScriptAsync hands back a JSON literal; the page returned a JSON
    # *string*, so decode twice (same shape the info file stores).
    $inner = $raw | ConvertFrom-Json
    if ($inner -is [string]) { $pageMetrics = $inner | ConvertFrom-Json } else { $pageMetrics = $inner }
  } catch { $pageMetrics = $null }
  if ($null -eq $pageMetrics) {
    if ($script:metricsLog -lt 3) { $script:metricsLog += 1; L ('METRICS unparsed: ' + [string]$raw) }
    return
  }
  $box = $pageMetrics.box
  $sil = $pageMetrics.model
  if ($null -eq $box -or $null -eq $sil) {
    if ($script:metricsLog -lt 3) { $script:metricsLog += 1; L ('METRICS incomplete: ' + [string]$raw) }
    return
  }

  $r = New-Object PetHost.Native+RECT
  if (-not [PetHost.Native]::GetWindowRect($script:hwnd, [ref]$r)) { return }
  $wpx = $r.Right - $r.Left
  $hpx = $r.Bottom - $r.Top
  $scale = 1.0
  if ($W -gt 0 -and $H -gt 0) { $scale = $wpx / [double]$W }

  # page CSS px -> screen px (the window has no border: client origin = window origin).
  # Boxes arrive in two shapes: {x,y,width,height} (PixiJS) and {left,top,width,height}
  # (DOM getBoundingClientRect), so read either pair.
  function ConvertTo-ScreenBox($b) {
    if ($null -eq $b) { return $null }
    $bx = 0.0; $by = 0.0
    if ($null -ne $b.x) { $bx = [double]$b.x } elseif ($null -ne $b.left) { $bx = [double]$b.left }
    if ($null -ne $b.y) { $by = [double]$b.y } elseif ($null -ne $b.top) { $by = [double]$b.top }
    $bw = if ($null -ne $b.width) { [double]$b.width } else { 0.0 }
    $bh = if ($null -ne $b.height) { [double]$b.height } else { 0.0 }
    $x = $bx * $scale
    $y = $by * $scale
    return [ordered]@{
      left   = [int][math]::Round($r.Left + $x)
      top    = [int][math]::Round($r.Top + $y)
      right  = [int][math]::Round($r.Left + $x + $bw * $scale)
      bottom = [int][math]::Round($r.Top + $y + $bh * $scale)
    }
  }

  $screenBox = ConvertTo-ScreenBox $box
  $screenModel = ConvertTo-ScreenBox $sil
  $screenLabel = ConvertTo-ScreenBox $pageMetrics.label
  $screenDetail = ConvertTo-ScreenBox $pageMetrics.detail
  $gaps = [ordered]@{
    # the two hard constraints from the brief: both must stay >= 0
    labelTopMinusModelTop = $(if ($null -ne $screenLabel -and $null -ne $screenModel) { $screenLabel.top - $screenModel.top } else { $null })
    modelRightMinusLabelRight = $(if ($null -ne $screenLabel -and $null -ne $screenModel) { $screenModel.right - $screenLabel.right } else { $null })
  }

  $doc = [ordered]@{
    ok = $true
    at = [int64]([datetime]::UtcNow - (New-Object System.DateTime(1970, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc))).TotalMilliseconds
    host = 'pet/host/host.ps1'
    pid = $PID
    parentPid = $ParentPid
    window = [ordered]@{ x = $r.Left; y = $r.Top; width = $wpx; height = $hpx }
    scale = $scale
    page = [ordered]@{
      box = $box; model = $sil; label = $pageMetrics.label; detail = $pageMetrics.detail
      samples = $pageMetrics.samples; viewport = $pageMetrics.viewport; extract = $pageMetrics.extract
      profile = $pageMetrics.profile; geom = $pageMetrics.geom
    }
    screen = [ordered]@{ box = $screenBox; model = $screenModel; label = $screenLabel; detail = $screenDetail }
    gaps = $gaps
  }
  $text = $doc | ConvertTo-Json -Depth 8
  # The document carries the whole row profile (a few tens of KB), so it is only
  # rewritten when the geometry or the label actually changed - plus a refresh
  # every MetricsRefreshSec so `at` never lags the panel's 15 s staleness window.
  $stable = (($screenModel | ConvertTo-Json -Compress) + '|' + ($screenLabel | ConvertTo-Json -Compress) + '|' + [string]$pageMetrics.samples)
  $now = Get-Date
  if ($stable -ne $script:metricsStable -or ($now - $script:metricsWrittenAt).TotalSeconds -ge 5) {
    $script:metricsStable = $stable
    $script:metricsWrittenAt = $now
    try {
      $tmp = $Metrics + '.tmp'
      [IO.File]::WriteAllText($tmp, $text, (New-Object System.Text.UTF8Encoding($false)))
      Move-Item -LiteralPath $tmp -Destination $Metrics -Force
    } catch {
      L ('cannot write metrics: ' + $_.Exception.Message)
    }
  }
  if ($script:metricsLog -lt 3) {
    $script:metricsLog += 1
    L ('METRICS model screen=' + (($screenModel | ConvertTo-Json -Compress)) + ' label=' + (($screenLabel | ConvertTo-Json -Compress)))
  }
}

function Write-Info {
  param($page)
  try {
    $obj = [ordered]@{
      ok = $true
      host = 'WPF + WebView2 (pet/host/host.ps1)'
      pid = $PID
      parentPid = $ParentPid
      hwnd = '0x' + $script:hwnd.ToString('x')
      bounds = @{ x = $X; y = $Y; width = $W; height = $H }
      topmost = $script:win.Topmost
      clickThrough = [bool](([int64][PetHost.Native]::GetWindowLongPtr($script:hwnd, $GWL_EXSTYLE)) -band $WS_EX_TRANSPARENT)
      allowsTransparency = $script:win.AllowsTransparency
      windowBackground = $script:win.Background.ToString()
      webviewDefaultBackground = $script:wv.DefaultBackgroundColor.ToString()
      runtime = $script:wv.CoreWebView2.Environment.BrowserVersionString
      url = $script:wv.Source.ToString()
      userDataFolder = $udd
      page = $page
    }
    Set-Content -Path $Info -Value ($obj | ConvertTo-Json -Depth 6) -Encoding UTF8
  } catch {
    L ('cannot write info file: ' + $_.Exception.Message)
  }
}

$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(300)
$timer.Add_Tick({
  if ($script:exiting) { return }

  if ($script:phase -eq 0) {
    if (-not $script:wv.IsLoaded) { return }
    try {
      $script:envTask = [Microsoft.Web.WebView2.Core.CoreWebView2Environment]::CreateAsync($null, $udd, $null)
      $script:phase = 1
      L 'CoreWebView2Environment.CreateAsync called'
    } catch {
      L ('FATAL CreateAsync: ' + $_.Exception.ToString())
      Exit-Host 'create-async-failed'
    }
    return
  }

  if ($script:phase -eq 1) {
    if (-not $script:envTask.IsCompleted) { return }
    if ($script:envTask.IsFaulted) {
      L ('FAULT env: ' + $script:envTask.Exception.ToString())
      Exit-Host 'environment-faulted'
      return
    }
    try {
      $script:coreTask = $script:wv.EnsureCoreWebView2Async($script:envTask.Result)
      $script:phase = 2
      L 'EnsureCoreWebView2Async called'
    } catch {
      L ('FAULT EnsureCoreWebView2Async: ' + $_.Exception.ToString())
      Exit-Host 'ensure-threw'
    }
    return
  }

  if ($script:phase -eq 2) {
    if ($null -eq $script:coreTask -or -not $script:coreTask.IsCompleted) { return }
    if ($script:coreTask.IsFaulted) {
      L ('FAULT core: ' + $script:coreTask.Exception.ToString())
      Exit-Host 'core-faulted'
      return
    }
    try {
      $core = $script:wv.CoreWebView2
      L ('core ready runtime=' + $core.Environment.BrowserVersionString)
      $core.SetVirtualHostNameToFolderMapping('pet.local', $petRoot, [Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
      $script:wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
      # The page can report diagnostics back (the ?selftest=1 expression run and
      # any reaction error).  They land next to this script so a verification run
      # can read them; nothing is sent the other way.
      try {
        # NOTE: the second parameter must NOT be called $args - that is a
        # PowerShell automatic variable and binding to it silently yields ''.
        $core.add_WebMessageReceived({
          param($sender, $e)
          try {
            $json = [string]$e.WebMessageAsJson
            [IO.File]::WriteAllText($script:pageMessagePath, $json, (New-Object System.Text.UTF8Encoding($false)))
            L ('PAGE ' + $json.Substring(0, [Math]::Min(400, $json.Length)))
          } catch { }
        })
      } catch { L ('web message hook failed: ' + $_.Exception.Message) }
      $url = "https://pet.local/$Page"
      if ($query) { $url += "?$query" }
      L ('navigating to ' + $url)
      $script:wv.Source = New-Object System.Uri $url
      $script:phase = 3
      $script:ticks = 0
    } catch {
      L ('FAULT navigate: ' + $_.Exception.ToString())
      Exit-Host 'navigate-threw'
    }
    return
  }

  if ($script:phase -eq 3) {
    # give the model time to load (moc3 + 2 textures + physics), then probe the
    # page the way pet\renderer\README.md does
    $script:ticks += 1
    if ($script:ticks -lt 22) { return }
    try {
      $script:probeTask = $script:wv.CoreWebView2.ExecuteScriptAsync('JSON.stringify({ready:!!window.__PET_READY__,alpha:(window.PetAPI&&PetAPI.alphaProbe)?PetAPI.alphaProbe():null,state:(window.PetAPI&&PetAPI.getState)?PetAPI.getState():null,motionGroups:(window.PetAPI&&PetAPI.motionGroups)?PetAPI.motionGroups():null,settingsMotions:(window.PetAPI&&PetAPI.settingsMotions)?PetAPI.settingsMotions():null,expressions:(window.PetAPI&&PetAPI.expressions)?PetAPI.expressions():null})')
      $script:phase = 4
      $script:ticks = 0
    } catch {
      L ('probe failed: ' + $_.Exception.Message)
      $script:phase = 4
    }
    return
  }

  if ($script:phase -eq 4) {
    $script:ticks += 1
    if ($null -ne $script:probeTask -and $script:probeTask.IsCompleted) { $script:probe = $script:probeTask.Result }
    if ($null -eq $script:probe -and $script:ticks -lt 20) { return }
    if ($ClickThrough) {
      $ex = [int64][PetHost.Native]::GetWindowLongPtr($script:hwnd, $GWL_EXSTYLE)
      $ex = $ex -bor $WS_EX_TRANSPARENT
      [void][PetHost.Native]::SetWindowLongPtr($script:hwnd, $GWL_EXSTYLE, [IntPtr]$ex)
    }
    Write-Info $script:probe
    L ('INFO page=' + [string]$script:probe)
    $script:phase = 5
    if ($Hold -gt 0) { $script:deadline = (Get-Date).AddSeconds($Hold) }
    return
  }

  # phase 5: stay alive, re-assert topmost for real, watch the parent and the
  # stop file.  The panel re-asserts its own topmost on a 2 s timer; this 1.5 s
  # cadence is deliberately the faster of the two so the pet wins the tie when
  # the two windows overlap, without either one fighting forever.
  $script:maintainTick += 1
  if ($script:maintainTick -ge 5) {
    $script:maintainTick = 0
    [void][PetHost.Native]::SetWindowPos($script:hwnd, $HWND_TOPMOST, 0, 0, 0, 0, ($SWP_NOMOVE -bor $SWP_NOSIZE -bor $SWP_NOACTIVATE))
    # Ask the page where the CHARACTER is (not where the window is) and publish it
    # for the panel: ui\widget.ps1 aligns its right edge with `screen.model.right`.
    Request-Metrics
  }
  if ($null -ne $script:metricsTask -and $script:metricsTask.IsCompleted) { Collect-Metrics }
  if ($ParentPid -gt 0) {
    $alive = $true
    try { $null = [System.Diagnostics.Process]::GetProcessById($ParentPid) } catch { $alive = $false }
    if (-not $alive) { Exit-Host 'parent gone'; return }
  }
  if ($StopFile -and (Test-Path -LiteralPath $StopFile)) { Exit-Host 'stop file'; return }
  # ---- development capture channel -----------------------------------------
  # `pet\host\force-state.json` lets a screenshot run drive the page through the
  # channel the page already documents (window.postMessage -> pet-state / pet-force)
  # WITHOUT touching the engine's state.json (which it rewrites every 2 s) and
  # without opening a second pet window: the production window, geometry and
  # WebView2 settings stay exactly as they are.  The file is absent in normal
  # operation, so this costs nothing when nobody is shooting a showcase.
  # every tick (300 ms): a screenshot run rewrites this file faster than 1.5 s per
  # state, so gating the check on every fifth tick would show the previous state.
  $forceText = ''
  try {
    if (Test-Path -LiteralPath $script:forceStatePath) {
      $forceText = [System.IO.File]::ReadAllText($script:forceStatePath, [System.Text.UTF8Encoding]::new($false))
    }
  } catch { $forceText = '' }
  if ($forceText -ne $script:forceSeen) {
    $script:forceSeen = $forceText
    try {
      $payload = if ([string]::IsNullOrWhiteSpace($forceText)) { 'null' } else { $forceText }
      [void]$script:wv.CoreWebView2.ExecuteScriptAsync('window.postMessage({type:"pet-force",payload:' + $payload + '},"*")')
      L ('force-state applied (' + $payload.Length + ' bytes)')
    } catch { L ('force-state failed: ' + $_.Exception.Message) }
  }
  # Same idea for the in-frame parameter watch (acceptance readings, and the
  # "is anything looping while idle" probe): pet\host\watch.json ->
  # {type:'pet-watch', payload}; the page answers over the web-message channel.
  $watchText = ''
  try {
    if (Test-Path -LiteralPath $script:watchPath) {
      $watchText = [System.IO.File]::ReadAllText($script:watchPath, [System.Text.UTF8Encoding]::new($false))
    }
  } catch { $watchText = '' }
  if ($watchText -ne $script:watchSeen) {
    $script:watchSeen = $watchText
    if (-not [string]::IsNullOrWhiteSpace($watchText)) {
      try {
        [void]$script:wv.CoreWebView2.ExecuteScriptAsync('window.postMessage({type:"pet-watch",payload:' + $watchText + '},"*")')
        L ('pet-watch applied (' + $watchText.Length + ' bytes)')
      } catch { L ('pet-watch failed: ' + $_.Exception.Message) }
    }
  }
  if ($null -ne $script:deadline -and (Get-Date) -ge $script:deadline) { Exit-Host 'hold elapsed' }
})
$script:timer = $timer
$timer.Start()

$win.Add_Closed({ Exit-Host 'window closed' })

L 'dispatcher run'
[System.Windows.Threading.Dispatcher]::Run()
L 'DONE'

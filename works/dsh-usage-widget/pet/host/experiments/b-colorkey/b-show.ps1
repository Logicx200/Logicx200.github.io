# b-show.ps1 -- EXPERIMENT B: Win32 colour-key layering.
#   * WinForms top-level window, FormBorderStyle=None, WS_EX_LAYERED + SetLayeredWindowAttributes(
#     colorKey = pure magenta, LWA_COLORKEY)
#   * the window's own background is pure magenta (#FF00FF)
#   * LEFT half  : a WebView2 child (its page background is also pure magenta, plus a blue circle)
#   * RIGHT half : no child at all -- pure parent magenta, plus one parent-drawn green box
# If the colour key works, magenta is punched out and the desktop shows through. If WebView2's
# GPU-composited content is NOT affected by the key, the left half stays a solid magenta block.
# PURE ASCII.
param(
  [int]$X = 60, [int]$Y = 60, [int]$W = 520, [int]$H = 320,
  [int]$Hold = 40,
  [string]$Info = ''
)
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$lib = Join-Path $here '..\lib\webview2'
if (-not $Info) { $Info = Join-Path $here 'b.json' }
$log = Join-Path $here 'b-show.log'
function L($m) { Add-Content -Path $log -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $m) -Encoding UTF8 }
Set-Content -Path $log -Value '' -Encoding UTF8

$MAGENTA = 0x00FF00FF   # COLORREF 0x00BBGGRR
$LWA_COLORKEY = 0x1
$GWL_EXSTYLE = -20
$WS_EX_LAYERED = 0x00080000

try {
  Add-Type -Namespace EXPN -Name N -MemberDefinition @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode)] public static extern bool SetDllDirectory(string path);
[DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr h, uint key, byte alpha, uint flags);
[DllImport("user32.dll", EntryPoint="GetWindowLongPtr")] public static extern IntPtr GetWindowLongPtr(IntPtr h, int n);
[DllImport("user32.dll", EntryPoint="SetWindowLongPtr")] public static extern IntPtr SetWindowLongPtr(IntPtr h, int n, IntPtr v);
[DllImport("user32.dll")] public static extern bool GetLayeredWindowAttributes(IntPtr h, out uint key, out byte alpha, out uint flags);
'@
  [void][EXPN.N]::SetDllDirectory($lib)
  $env:PATH = $lib + ';' + $env:PATH
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $lib 'Microsoft.Web.WebView2.Core.dll'))
  [void][System.Reflection.Assembly]::LoadFrom((Join-Path $lib 'Microsoft.Web.WebView2.WinForms.dll'))
  L 'assemblies ok'

  $html = @'
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;width:100%;height:100%;background:#FF00FF;overflow:hidden}
#dot{position:absolute;left:20px;top:60px;width:170px;height:170px;border-radius:50%;background:#1e6bff}
#n{position:absolute;left:14px;top:14px;color:#000;font:14px Consolas;background:#fff;padding:3px}
</style></head><body>
<div id="dot"></div><div id="n">page clicks: <span id="c">0</span></div>
<script>
window.__clicks = 0
function post(kind, e){
  try { window.chrome.webview.postMessage(JSON.stringify({ kind: kind, x: e.clientX, y: e.clientY, n: window.__clicks })) } catch (err) { }
}
function bump(e){ window.__clicks++; document.getElementById('c').textContent = window.__clicks; post('down', e) }
document.addEventListener('mousedown', bump, true)
document.addEventListener('pointerdown', bump, true)
document.addEventListener('mousemove', function(e){
  if (!window.__mv || Date.now() - window.__mv > 500) { window.__mv = Date.now(); post('move', e) }
}, true)
setTimeout(function(){ post('ready', {clientX:0,clientY:0}) }, 120)
</script></body></html>
'@

  $form = New-Object System.Windows.Forms.Form
  $form.Text = 'PET-EXP-B'
  $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
  $form.StartPosition = 'Manual'
  $form.Location = New-Object System.Drawing.Point $X, $Y
  $form.Size = New-Object System.Drawing.Size $W, $H
  $form.BackColor = [System.Drawing.Color]::FromArgb(255, 0, 255)   # pure magenta = the key
  $form.ShowInTaskbar = $false
  $form.TopMost = $true

  # parent-drawn green box on the RIGHT half (proves the parent surface itself is keyed/painted)
  $green = New-Object System.Windows.Forms.Panel
  $green.BackColor = [System.Drawing.Color]::FromArgb(0, 200, 80)
  $green.Location = New-Object System.Drawing.Point ([int]($W * 0.62)), 60
  $green.Size = New-Object System.Drawing.Size 150, 150
  $form.Controls.Add($green)

  # WebView2 child on the LEFT half only
  $wv = New-Object Microsoft.Web.WebView2.WinForms.WebView2
  $wv.Location = New-Object System.Drawing.Point 0, 0
  $wv.Size = New-Object System.Drawing.Size ([int]($W / 2)), $H
  $wv.DefaultBackgroundColor = [System.Drawing.Color]::Transparent
  $form.Controls.Add($wv)

  $form.Show()
  [System.Windows.Forms.Application]::DoEvents()
  $hwnd = $form.Handle

  # apply the colour key to the top-level window
  $ex = [int64][EXPN.N]::GetWindowLongPtr($hwnd, $GWL_EXSTYLE)
  [void][EXPN.N]::SetWindowLongPtr($hwnd, $GWL_EXSTYLE, [IntPtr]($ex -bor $WS_EX_LAYERED))
  $ok = [EXPN.N]::SetLayeredWindowAttributes($hwnd, $MAGENTA, 0, $LWA_COLORKEY)
  $k = 0; $a = 0; $f = 0
  [void][EXPN.N]::GetLayeredWindowAttributes($hwnd, [ref]$k, [ref]$a, [ref]$f)
  L ("hwnd=0x{0:x} SetLayeredWindowAttributes={1} key=0x{2:x8} alpha={3} flags={4} exStyle=0x{5:x}" -f $hwnd.ToInt64(), $ok, $k, $a, $f, ([int64][EXPN.N]::GetWindowLongPtr($hwnd, $GWL_EXSTYLE)))

  $script:clicks = -1
  $script:msgs = New-Object System.Collections.ArrayList
  $script:lastMsg = ''
  $script:phase = 0
  $script:task = $null
  $script:deadline = (Get-Date).AddSeconds($Hold)

  $script:write = {
    $json = [pscustomobject]@{
      hwnd = $hwnd.ToInt64(); x = $X; y = $Y; w = $W; h = $H
      colorKeyApplied = $ok
      layeredKey = ('0x{0:x8}' -f $k)
      pageClicks = $script:clicks
      messageCount = $script:msgs.Count
      lastMessage = $script:lastMsg
      probes = [pscustomobject]@{
        # NOTE: the WebView2 child covers form x 0..W/2, so a "parent-only" probe must sit in the
        # RIGHT half. My first version put q1 at x+30, which is inside the child -- mislabeled.
        q1_parent_magenta  = @{ x = $X + 340; y = $Y + 280 }
        q2_parent_green    = @{ x = $X + 380; y = $Y + 130 }
        q3_child_magenta   = @{ x = $X + 220; y = $Y + 280 }
        q4_child_blue      = @{ x = $X + 105; y = $Y + 145 }
      }
    } | ConvertTo-Json -Depth 6
    Set-Content -Path ($Info + '.tmp') -Value $json -Encoding UTF8
    Move-Item -Path ($Info + '.tmp') -Destination $Info -Force
  }

  $timer = New-Object System.Windows.Forms.Timer
  $timer.Interval = 400
  $timer.Add_Tick({
    if ($script:phase -eq 0) {
      $script:task = $wv.EnsureCoreWebView2Async($null)
      $script:phase = 1
      L 'EnsureCoreWebView2Async called'
      return
    }
    if ($script:phase -eq 1) {
      if (-not $script:task.IsCompleted) { return }
      if ($script:task.IsFaulted) { L ('FAULT ' + $script:task.Exception.ToString()); $script:phase = 9; return }
      $core = $wv.CoreWebView2
      $core.add_WebMessageReceived({
        param($sender, $ev)
        $raw = ''
        try { $raw = [string]$ev.WebMessageAsJson } catch { L ('msg threw ' + $_.Exception.Message) }
        $script:lastMsg = $raw
        [void]$script:msgs.Add($raw)
        L ('MSG ' + $raw)
        try {
          $o = $raw | ConvertFrom-Json
          if ($o -is [string]) { $o = $o | ConvertFrom-Json }
          if ($o.kind -eq 'down') { $script:clicks = [int]$o.n }
        } catch { }
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
        $timer.Stop(); $wv.Dispose(); $form.Close()
      }
    }
  })
  $timer.Start()
  [System.Windows.Forms.Application]::Run($form)
  L 'done'
} catch {
  L ('EXCEPTION ' + $_.Exception.ToString())
}

<#
  dsh-usage-widget / ui / widget.ps1
  ---------------------------------------------------------------------------
  The WINDOW of the standalone DSH usage widget: a small, semi-transparent,
  always-on-top, click-through-capable instrument panel pinned to the
  bottom-right corner of the work area.

  Runtime: Windows PowerShell 5.1 (STA), WPF + WinForms (tray) + GDI+ (icon).
  No build step, no dependencies.  This file is UTF-8 WITH BOM (PS 5.1 needs
  the BOM to read the Chinese literals below).

  Start it the boring way - a per-user logon task or the Start Menu shortcut
  that install-startup.ps1 creates, and nothing else:
      powershell.exe -NoProfile -File "<...>\ui\widget.ps1"
  There is deliberately no .cmd / .bat launcher: a batch file whose body runs
  PowerShell with a hidden window and a bypassed execution policy is the
  classic defence-evasion shape, and 火绒 (Huorong) was right to quarantine the
  one this project used to ship.  The console this process owns is hidden from
  the inside instead, by HideOwnConsole() in the Win32 helper below.

  Layout (top -> bottom, the window is bottom-anchored and grows upwards):
      [ hint: engine state, dim, only when the engine is not connected ]
      [ toast area: a history, one line per toast, newest nearest the footer,
        at most 5; nothing fades and nothing expires - the sixth line simply
        pushes the oldest one out; every token line carries the local
        HH:MM:SS of its engine event; 命中 green, 未命中 red, rest neutral ]
      [ thin separator rule                                              ]
      [ agents: summary + at most agentsMax rows, drawn only when the
        snapshot reports agents, followed by a second thin separator rule ]
      [ jobs: summary + at most jobsMax two-line rows, drawn only when the
        snapshot reports background programs                              ]
      [ fixed 4-line footer Grid: today / peak / total / balance          ]

  Companion window: the Live2D pet (pet/host/host.ps1, WPF + WebView2) is started,
  positioned, hidden/shown and stopped by this process - the panel remains the
  single entry point, and its own launch line is unchanged.  The pet window is
  anchored to the work area's bottom-right corner on its own and never looks at
  the panel; the host then MEASURES the character on the page (PixiJS bounds plus
  an alpha scan of the rendered frame) and publishes its screen box in
  pet\host\model.json, and this panel aligns its own right edge with the
  character's right edge.  So panel.right == model.right, and the pet's body
  covers the panel's bottom-right corner without touching a single text rect
  (checked with the per-row outline profile and pixel by pixel).  The panel also
  publishes, for the page, where the status label should sit
  (pet\renderer\panel-geometry.json): right-aligned with its own right-aligned text
  and 12 px below the text line above it - both measured from its live layout, so
  padding or font changes flow through.
  The pair sits close to the taskbar: the pet window's bottom is PetMarginY above
  the work area's bottom and the model is shifted a further PetModelShiftY down
  inside its window, which the panel's bottom follows (that is the "整体往下" of
  task-5).  The pet is re-asserted topmost every 1.5 s against the panel's own 2 s,
  hides and shows with the panel, and is stopped on exit.  Its label is drawn from
  pet/renderer/state.json, which the ENGINE writes out of pet/state.mjs
  (pet/STATE-PROTOCOL.md): the panel never decides a pet state.

  Engine bridge: engine/cli.mjs is started with the bundled node.exe with
  stdout+stderr redirected.  Output is read asynchronously by
  Register-ObjectEvent (OutputDataReceived / ErrorDataReceived) whose action
  runs on a background runspace; it only enqueues raw lines into a thread-safe
  ConcurrentQueue.  A DispatcherTimer on the UI thread drains that queue, so
  every UI mutation happens on the dispatcher thread and the window never
  blocks or is touched from a foreign thread.

  Decisions taken where the spec was open (all documented here on purpose):
    * Console: HideOwnConsole() hides the console only when this process is the
      only one attached to it (GetConsoleProcessList == 1), i.e. when the
      console was created for us by the launcher.  Launched from an existing
      terminal the console is shared and is left alone on purpose, so running
      the widget by hand never blanks the shell that started it.  No console at
      all (GetConsoleWindow() == 0) is a silent no-op - so is every other path.
    * Footer: a real WPF Grid with one column per field instead of padded
      strings, so the ￥ column, the $ column and the token column each end on a
      straight vertical edge on every row.  Padding CJK text with spaces cannot
      do that: the label column is Chinese and the face is monospace.
    * Toast colours: only the two upload lines are coloured - 命中 green,
      未命中 red.  下载 lines, engine messages, the dim hint, the separator and
      the entire footer keep exactly the colours they had before ("stays white"
      is read as "stays as it is": neutral, neither green nor red).
    * Window width: derived from fontSize (22.7 em of content + 22 px of chrome)
      so a larger font can never wrap or trim a line - at 14 px that is 340 px.
    * Money: the spec's rule "￥/$ with 4 decimals" wins over the 2-decimal
      ￥53.48 in the sample footer -> today/total always use 4 decimals.
      The balance line is the exception: the spec says it is shown "exactly as
      the engine reports it" (sample ￥8.47), so a numeric balance is shown
      with 2 decimals and a string balance verbatim.
    * Toast cost split: one rule, used everywhere - the call's costCny is split
      across the three token categories in proportion to that call's token
      counts (share_i = tokens_i / (hit+miss+out)).  A category with 0 tokens
      never produces a toast, so its share is never shown.
    * Tiny amounts: 4 decimals, but if a non-zero amount would round to
      0.0000 the toast switches to 6 decimals so it stays meaningful.
    * Peak/off-peak is computed locally from UTC (Mon-Fri, 01:00-04:00 and
      06:00-10:00 = 峰时, half-open intervals); the engine's own peak flag is
      ignored so the footer line works even while the engine is down.
    * The engine child runs for the whole lifetime of the widget (it is the
      recorder); only window *visibility* follows the DSH process.
    * The widget is a resident: Topmost + ShowActivated=false +
      WS_EX_NOACTIVATE, so it never steals focus, and it re-asserts its
      position/topmost on a slow timer in case something moves it.
    * Toast timestamps: an engine event's `at` (epoch milliseconds) is turned
      into LOCAL time and printed as "HH:MM:SS " in front of the line.  The
      prefix is part of the same TextBlock, so the whole line - prefix
      included - keeps the single colour it already had (there is no second,
      dimmer timestamp column).  A missing or nonsensical `at` (anything
      outside 2000..2100) falls back to the current local time, so a line can
      never be printed without one.
    * Agents / jobs sections: rendered from the last snapshot alone, so an
      engine that does not report the key yet - or reports an empty array -
      shows nothing at all: no row, no separator.  Both sections are cleared
      when the engine goes away, so no stale agent survives a crash.
    * The agent section owns the second separator rule: the rule lives INSIDE
      the section's StackPanel, so hiding the section hides the rule with it
      and an empty agent list can never leave a stray line behind.  Order is
      therefore: toasts | rule | agents | rule | jobs | footer.
    * Agent rows: running first, snapshot order preserved inside each group (no
      sort by elapsed - the engine's order is the meaningful one), at most
      agentsMax of them, then a "+N" marker on the summary line when more
      exist.  The label is a TextBlock with TextTrimming=CharacterEllipsis in
      a star column, so a long name is ellipsised by WPF at whatever width is
      left and the row can never wrap.  A state that is not exactly "running"
      (idle, empty, anything new the engine invents) counts as 空闲.
    * Job rows: the percentage / "剩余" block is right-aligned in a star column
      so two jobs' numbers land on the same edge; the elapsed column sits after
      the program name.  The command on the second line is ellipsised the same
      way; when the job carries no command the id is shown instead, and when it
      has neither the second line is dropped rather than left blank.
    * Window width: the timestamp widens the worst-case toast to 27.09 em
      ('00:12:47 上传 未命中 4,500,000tokens -￥0.000002' measured in Cascadia
      Code at 14 px -> 379.3 px), so the coefficient moved from 22.7 em to
      27.2 em.  Both new sections are narrower than that.
    * Pet launch: the panel starts pet/host/host.ps1 with powershell.exe
      -NoProfile -File (the same boring shape as the panel's own launcher: no
      hidden-window flag, no bypass, no encoded command) and supervises it: one
      host per panel, restarted at most every 30 s if it dies, moved with
      SetWindowPos/FindWindow('DSH pet') on every placement update, hidden and
      shown with the panel, and asked to leave through a stop file before being
      killed.  dshRunning for the pet state is published as a heartbeat file in
      the per-user temp directory, which the engine reads - see the note in
      engine/pet-state.mjs.  -NoPet and -PetWidth/-PetHeight exist for
      development runs; the scheduled task passes none of them.
    * Pet size and placement: 340x340, the model at 0.735 of its fitted size
      anchored to the window's bottom-right and shifted by the host: 16 px left
      (-ModelShiftX) so the physics-driven tail is not cut by the window's right
      edge, and 24 px down (-ModelShiftY) into the transparent space under the
      character so the pair sits 13 px above the work area's bottom.  The pet
      window itself is PetMarginX = 18 / PetMarginY = 4 from the work area's
      bottom-right corner.  The panel's right edge is the measured character right
      edge and its bottom is wa.Bottom - PetMarginY - petH/2 + PetModelShiftY, so
      the panel rides down with the model and grows upwards as toasts arrive.
      The label anchors (right edge + 12 px below the footer's token line) are
      published to the page as pet\renderer\panel-geometry.json.  The clamps in
      Get-WidgetPlacement degrade sanely on a smaller monitor, and -NoPet /
      -PetWidth / -PetHeight / -PetFill exist for development runs only (the
      scheduled task passes none of them).
#>
[CmdletBinding()]
param(
    # Path to engine/cli.mjs (defaults to ..\engine\cli.mjs next to ui\).
    [string]$EnginePath,
    # Bundled node.exe (defaults to the documented runtime location).
    [string]$NodePath = 'C:\Users\x1503\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe',
    # Path to the shared config.json (defaults to ..\config.json).
    [string]$ConfigPath,
    # --- development / verification only, never used by the launcher --------
    [switch]$ForceShow,               # show the window even if DSH is absent
    [string]$DevSnapshot,             # render the window to this PNG path
    [int]$DevSnapshotDelayMs = 0,     # ... after this delay
    [switch]$DevExitAfterSnapshot,
    [switch]$DevClickThrough,            # apply click-through and log the style bits
    # --- the Live2D pet (started and supervised by this panel) --------------
    # The pet window keeps a quarter of its bounding box inside this panel
    # (X = panel.right - petW/2, Y = panel.bottom - petH/2) and the pair is
    # anchored by their UNION to the work area's bottom-right corner, so neither
    # window can leave the work area.  pet/host/host.ps1 -AnchorBr then keeps the
    # character itself in the pet window's bottom-right, clear of the panel text.
    [int]$PetWidth = 340,
    [int]$PetHeight = 340,
    [double]$PetFill = 0.735,
    [switch]$NoPet                      # development / panel-only screenshots
)

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# 0. our own console, and the Win32 window styles used further down
# --------------------------------------------------------------------------
# The launcher is deliberately boring -- `powershell.exe -NoProfile -File ...`,
# no hidden-window flag, no execution-policy bypass, no encoded command -- so
# the console window the launcher gives us is hidden from the inside, here,
# before the slow assembly load below (it is only on screen for the moment it
# takes to compile this type).
#   * no console attached -> GetConsoleWindow() returns 0        -> no-op
#   * a console shared with other processes (started from an
#     existing terminal)  -> GetConsoleProcessList() > 1         -> left alone
#   * a console of our own (logon task, shortcut, Start-Process)  -> SW_HIDE
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DshWin32 {
    // --- window styles: click-through + "never activate me" ---------------
    public const int GWL_EXSTYLE      = -20;
    public const int WS_EX_TRANSPARENT = 0x00000020;
    public const int WS_EX_LAYERED     = 0x00080000;
    public const int WS_EX_TOOLWINDOW  = 0x00000080;
    public const int WS_EX_NOACTIVATE  = 0x08000000;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll", SetLastError = true, EntryPoint = "GetWindowLongPtr")]
    private static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll", SetLastError = true, EntryPoint = "SetWindowLongPtr")]
    private static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

    public static int GetExStyle(IntPtr hWnd) {
        if (IntPtr.Size == 8) return (int)GetWindowLongPtr(hWnd, GWL_EXSTYLE).ToInt64();
        return GetWindowLong(hWnd, GWL_EXSTYLE);
    }
    public static void SetExStyle(IntPtr hWnd, int style) {
        if (IntPtr.Size == 8) { SetWindowLongPtr(hWnd, GWL_EXSTYLE, new IntPtr(style)); return; }
        SetWindowLong(hWnd, GWL_EXSTYLE, style);
    }

    // --- console ----------------------------------------------------------
    public const int SW_HIDE = 0;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GetConsoleWindow();
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern uint GetConsoleProcessList(IntPtr[] processList, uint count);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    /// Hide the console window of this process, but only when it belongs to us
    /// alone.  Returns false (never throws) when there is nothing to hide.
    public static bool HideOwnConsole() {
        IntPtr h = GetConsoleWindow();
        if (h == IntPtr.Zero) return false;            // no console attached
        IntPtr[] procs = new IntPtr[8];
        uint n = GetConsoleProcessList(procs, (uint)procs.Length);
        if (n != 1) return false;                      // shared console: keep it
        return ShowWindow(h, SW_HIDE);
    }

    // --- the pet window: find it by title, move it, show/hide it -------------
    // The pet host is a separate process with its own window (title "DSH pet").
    // The panel never sends it messages: it just moves and shows/hides that
    // window directly, which cannot go stale and needs no IPC.
    public const int SW_SHOWNOACTIVATE = 4;
    public const uint SWP_NOSIZE     = 0x0001;
    public const uint SWP_NOMOVE     = 0x0002;
    public const uint SWP_NOACTIVATE = 0x0010;
    public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool IsWindow(IntPtr hWnd);

    public static IntPtr FindWindowByTitle(string title) { return FindWindow(null, title); }
    public static bool IsWindowAlive(IntPtr hWnd) { return hWnd != IntPtr.Zero && IsWindow(hWnd); }
    public static bool ShowWindowNoActivate(IntPtr hWnd, int nCmdShow) { return ShowWindow(hWnd, nCmdShow); }
    /// Move the window and put it back on top without activating it.  Passing
    /// HWND_TOPMOST is what re-asserts Topmost for real - setting the WPF
    /// property to the value it already has is a no-op.
    public static bool MoveTopmost(IntPtr hWnd, int x, int y, int w, int h) {
        return SetWindowPos(hWnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE);
    }
    public static bool ReassertTopmost(IntPtr hWnd) {
        return SetWindowPos(hWnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    }
}
'@

# Harmless when there is no console (or no user32): never let startup fail here.
try { [void][DshWin32]::HideOwnConsole() } catch { }

# WPF + WinForms (tray) + GDI+ (icon).  Loaded before the config is consumed:
# the config below already builds a WPF FontFamily from `fontFamily`.
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Xaml
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --------------------------------------------------------------------------
# 0. paths, config
# --------------------------------------------------------------------------
$script:UiDir   = Split-Path -Parent $PSCommandPath
$script:RootDir = Split-Path -Parent $script:UiDir
if (-not $EnginePath) { $EnginePath = Join-Path $script:RootDir 'engine\cli.mjs' }
if (-not $ConfigPath) { $ConfigPath = Join-Path $script:RootDir 'config.json' }
$script:EnginePath = $EnginePath
$script:NodePath   = $NodePath

# ---- the pet: paths and state -------------------------------------------
# The pet is a second window (pet/host/host.ps1, WPF + WebView2) started and
# supervised by THIS process.  The launch line of the panel itself is untouched:
# it is still `powershell.exe -NoProfile -File ui\widget.ps1`, and everything the
# pet needs is decided here.
$script:PetHostEnabled = -not $NoPet
$script:PetW           = [math]::Max(160, $PetWidth)
$script:PetH           = [math]::Max(160, $PetHeight)
$script:PetFill        = $(if ($PetFill -gt 0 -and $PetFill -le 1) { $PetFill } else { 0.735 })
$script:PetHostPath    = Join-Path $script:RootDir 'pet\host\host.ps1'
# A stop file and a heartbeat file, both in the per-user temp directory: ASCII
# there, per-user, and nothing of the sort is written into the project tree.
$script:PetStopFile       = Join-Path ([IO.Path]::GetTempPath()) 'dsh-usage-widget-pet.stop'
$script:DshHeartbeatFile  = Join-Path ([IO.Path]::GetTempPath()) 'dsh-usage-widget-dsh-running.json'
$script:PetProc        = $null
$script:PetHwnd        = [IntPtr]::Zero
$script:PetVisible     = $false
$script:PetNextStart   = [datetime]::MinValue
$script:PetWarned      = $false
# The host publishes the CHARACTER's measured screen box here (pet\host\model.json)
# and the panel aligns its right edge with it.  PetSilhouetteInsetPx is only the
# fallback used in the first seconds, before the model has been measured: how far
# the character's right edge sits inside the pet window's right edge (measured for
# the shipped geometry, and equal to what the host reports once measured).
$script:PetModelPath         = Join-Path $script:RootDir 'pet\host\model.json'
$script:PetModel             = $null
$script:PetModelReadAt       = [datetime]::MinValue
$script:PetSilhouetteInsetPx = 8
# ---- the pet/panel pair's position on the work area -------------------------
# PetMarginX keeps the horizontal position the user accepted in task-4 (the pet
# window's right edge 18 px in from the work area's right edge).  PetMarginY is
# the vertical twin and was reduced to 4 px, and the model is pushed a further
# PetModelShiftY = 24 px down inside its window (host -ModelShiftY), so the
# character's outline bottom now ends ~13 px above the work area's bottom instead
# of leaving 51 px of dead space.  The character must stay ABOVE the window's
# bottom edge: the measured silhouette has ~33 px of transparent space below it
# inside the model box, and 24 px of that is now used (verified in
# pet\host\model.json: screen.model.bottom < window.y + window.height).
$script:PetMarginX      = 18
$script:PetMarginY      = 4
$script:PetModelShiftX  = 16
$script:PetModelShiftY  = 24
# The panel's bottom rides on this shift (task-5's "整体往下"), so both windows always
# move together and panel.right == model.right holds by construction.  The pet window is
# pinned to the work area's bottom-right corner and is **not draggable** (task-13 removed
# the interaction layer: the pet must stay fully click-through, see host.ps1 -ClickThrough).
# The label anchors the panel publishes for the page (pet\renderer\panel-geometry.json):
# gap between the label's top edge and the bottom edge of the panel text line
# above it (the footer's right-hand token cell), in px.
$script:PetLabelGapY    = 12
$script:PetGeometryPath = Join-Path $script:RootDir 'pet\renderer\panel-geometry.json'
$script:PetGeometryAt   = [datetime]::MinValue
$script:PetGeometryText = ''

# defaults mirror config.json; config.json always wins when it has the key.
# toastLifeMs = 0 means "a toast never expires": history lines only ever leave
# when a newer line pushes them out.  There is no fade any more, so there is no
# toastFadeMs key either (an old config.json that still has one is ignored).
$cfg = @{
    toastMax    = 5
    toastLifeMs = 0
    agentsMax   = 3
    jobsMax     = 2
    opacity     = 0.86
    margin      = 18
    fontFamily  = 'Cascadia Code, Consolas'
    fontSize    = 14
}
try {
    if (Test-Path -LiteralPath $ConfigPath) {
        $raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
        $jc  = $raw | ConvertFrom-Json
        foreach ($k in @($cfg.Keys)) {
            $v = $null
            foreach ($p in $jc.PSObject.Properties) { if ($p.Name -ieq $k) { $v = $p.Value; break } }
            if ($null -ne $v -and "$v" -ne '') { $cfg[$k] = $v }
        }
    }
}
catch { Write-Verbose "config.json could not be read: $_" }

$script:ToastMax    = [int]$cfg.toastMax
$script:ToastLifeMs = [int]$cfg.toastLifeMs
# agentsMax / jobsMax: how many rows the two status sections draw.  The arrays
# themselves are never truncated - the summary line still counts everything and
# the agent summary carries the "+N" marker for what did not fit.
$script:AgentsMax   = [int]$cfg.agentsMax
$script:JobsMax     = [int]$cfg.jobsMax
if ($script:AgentsMax -lt 0) { $script:AgentsMax = 0 }
if ($script:JobsMax   -lt 0) { $script:JobsMax   = 0 }
$script:Margin      = [double]$cfg.margin
$script:FontFamily  = New-Object System.Windows.Media.FontFamily([string]$cfg.fontFamily)
$script:FontSize    = [double]$cfg.fontSize
$script:WinOpacity  = [double]$cfg.opacity

# One widget per session: a second copy would mean two panels and two tray icons.
# Skipped for the development switches so verification runs can always start.
$script:SingleInstance = $null
if (-not ($DevSnapshot -or $ForceShow)) {
    $script:SingleInstance = New-Object System.Threading.Mutex($false, 'Local\dsh-usage-widget-single-instance')
    $acquired = $false
    try { $acquired = $script:SingleInstance.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { exit 0 }
}


# --------------------------------------------------------------------------
# 1. small formatting helpers (no currency maths here - the engine converts)
# --------------------------------------------------------------------------
function Format-Tokens([double]$v) {
    if ($v -ge 999950) { return ('{0:0.#}M' -f ($v / 1000000.0)) }
    if ($v -ge 1000)   { return ('{0:0.#}K' -f ($v / 1000.0)) }
    return ('{0:N0}' -f $v)
}
function Format-Cny([double]$v)   { return ('￥{0:0.0000}' -f $v) }
function Format-Usd([double]$v)   { return ('${0:0.0000}' -f $v) }
function Format-Share([double]$v) {
    # 4 decimals is the documented minimum; go to 6 when 4 would print 0.0000
    $a = [math]::Abs($v)
    if ($a -gt 0 -and $a -lt 0.0001) { return ('{0:0.000000}' -f $a) }
    return ('{0:0.0000}' -f $a)
}
# 峰时 = Mon-Fri 01:00-04:00 and 06:00-10:00 UTC (half-open intervals)
function Test-PeakHour([datetime]$utc) {
    if ($utc.DayOfWeek -eq [System.DayOfWeek]::Saturday -or $utc.DayOfWeek -eq [System.DayOfWeek]::Sunday) { return $false }
    $h = $utc.Hour
    return ((($h -ge 1) -and ($h -lt 4)) -or (($h -ge 6) -and ($h -lt 10)))
}

# --- tolerant JSON field access -------------------------------------------
function Get-PropCI($obj, [string]$name) {
    if ($null -eq $obj) { return $null }
    if ($obj -is [string]) { return $null }
    foreach ($p in $obj.PSObject.Properties) { if ($p.Name -ieq $name) { return $p.Value } }
    return $null
}
function Get-First($obj, [string[]]$names) {
    if ($null -eq $obj) { return $null }
    foreach ($n in $names) {
        if ($n.IndexOf('.') -ge 0) {
            $cur = $obj
            foreach ($part in $n.Split('.')) {
                $cur = Get-PropCI $cur $part
                if ($null -eq $cur) { break }
            }
            if ($null -ne $cur) { return $cur }
        }
        else {
            $v = Get-PropCI $obj $n
            if ($null -ne $v) { return $v }
        }
    }
    return $null
}
function To-Num($v) {
    if ($null -eq $v) { return $null }
    if ($v -is [bool]) { return $null }
    if ($v -is [string]) {
        $d = 0.0
        if ([double]::TryParse($v, [ref]$d)) { return $d }
        return $null
    }
    try { return [double]$v } catch { return $null }
}
# engine/cli.mjs reports "today":{"tokens":{"hit":n,"miss":n,"out":n}}; the
# footer needs one number, so the triple is summed (a plain number also works).
function To-TokenCount($v) {
    if ($null -eq $v) { return $null }
    if ($v -is [string] -or $v -is [ValueType]) { return (To-Num $v) }
    $h = To-Num (Get-PropCI $v 'hit');  if ($null -eq $h) { $h = To-Num (Get-PropCI $v 'cacheHit') }
    $m = To-Num (Get-PropCI $v 'miss'); if ($null -eq $m) { $m = To-Num (Get-PropCI $v 'cacheMiss') }
    $o = To-Num (Get-PropCI $v 'out');  if ($null -eq $o) { $o = To-Num (Get-PropCI $v 'output') }
    if ($null -eq $h -and $null -eq $m -and $null -eq $o) { return (To-Num (Get-PropCI $v 'total')) }
    $sum = 0.0
    if ($null -ne $h) { $sum += $h }
    if ($null -ne $m) { $sum += $m }
    if ($null -ne $o) { $sum += $o }
    return $sum
}

# snapshot / event payloads are accepted at top level or one level down
function Get-Payload($o, [string[]]$probe) {
    if ($null -eq (Get-First $o $probe)) {
        foreach ($k in @('data', 'payload', 'snapshot', 'usage', 'stats', 'call', 'event')) {
            $inner = Get-PropCI $o $k
            if ($null -ne $inner -and $null -ne (Get-First $inner $probe)) { return $inner }
        }
    }
    return $o
}

# An array field ("agents", "jobs") is accepted at the top level or one level
# down, exactly like Get-Payload does for scalars.  Always returns an array -
# ConvertFrom-Json hands back a bare object for a one-element array - and an
# empty array for "key missing" and for "key present but []", because the two
# mean the same thing to the window: draw nothing.
function Get-ArrayField($o, [string[]]$names) {
    if ($null -eq $o) { return , @() }
    $v = Get-First $o $names
    if ($null -eq $v) {
        foreach ($k in @('data', 'payload', 'snapshot', 'status', 'usage', 'stats')) {
            $inner = Get-PropCI $o $k
            if ($null -ne $inner) {
                $v = Get-First $inner $names
                if ($null -ne $v) { break }
            }
        }
    }
    # No ,@() here on purpose: the caller wraps the result in @() as well, and
    # the comma idiom would hand it a one-element array whose single element is
    # the real array - an empty "agents" then became one phantom row instead of
    # no row at all.
    if ($null -eq $v) { return @() }
    return @($v)
}

# --- time ------------------------------------------------------------------
# 1970-01-01T00:00:00Z as a UTC-kind DateTime: the one epoch base that both
# Windows PowerShell 5.1 and PowerShell 7 agree on without a helper class.
$script:EpochUtc = New-Object System.DateTime(1970, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)

# Engine timestamps are epoch milliseconds and are shown in LOCAL time.
# Anything outside 2000..2100 is treated as "no timestamp at all" rather than
# rendered as a 1970 line: the caller then falls back to the current time.
function Test-EpochMs([double]$ms) {
    return ($ms -ge 946684800000 -and $ms -le 4102444800000)
}
function ConvertFrom-EpochMs([double]$ms) {
    return $script:EpochUtc.AddMilliseconds($ms).ToLocalTime()
}
function Get-EpochNowMs {
    return [double]([datetime]::UtcNow - $script:EpochUtc).TotalMilliseconds
}
# The clock stamp in front of every token line: local HH:MM:SS.
function Format-Clock([double]$ms) {
    return (ConvertFrom-EpochMs $ms).ToString('HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
}
# Elapsed / ETA: MM:SS, and H:MM:SS once it is an hour or longer (never "-").
function Format-Duration([double]$ms) {
    if ($null -eq $ms -or [double]::IsNaN($ms) -or $ms -lt 0) { $ms = 0 }
    $ts = [timespan]::FromMilliseconds([double]$ms)
    if ($ts.TotalHours -ge 1) {
        return ('{0}:{1:00}:{2:00}' -f [int][math]::Floor($ts.TotalHours), $ts.Minutes, $ts.Seconds)
    }
    return ('{0:00}:{1:00}' -f $ts.Minutes, $ts.Seconds)
}

# --------------------------------------------------------------------------
# 2. UI construction
# --------------------------------------------------------------------------
$xaml = @'
<Border xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Background="#F2181A1E" BorderBrush="#26FFFFFF" BorderThickness="1" CornerRadius="7"
        SnapsToDevicePixels="True" UseLayoutRounding="True">
  <Grid x:Name="ContentGrid" Margin="10,7,10,8">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <TextBlock x:Name="HintText" Grid.Row="0" Text="引擎未连接" Visibility="Collapsed"
               FontFamily="__FF__" FontSize="__FS__" Foreground="#79818C"
               TextTrimming="CharacterEllipsis" Margin="0,0,0,3"/>

    <StackPanel x:Name="ToastPanel" Grid.Row="1" VerticalAlignment="Bottom"/>

    <Border Grid.Row="2" Height="1" Background="#2EFFFFFF" Margin="0,6,0,6"/>

    <!-- Agent section.  Collapsed until a snapshot actually reports agents, and
         the second separator rule lives INSIDE it, so an empty agent list can
         never leave a stray rule on screen.  The rows themselves are built in
         code (New-AgentRow) into AgentList. -->
    <StackPanel x:Name="AgentsPanel" Grid.Row="3" Visibility="Collapsed">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" Text="智能体" Margin="0,0,10,0"
                   FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
        <TextBlock x:Name="AgentsSummary" Grid.Column="1" Text=""
                   FontFamily="__FF__" FontSize="__FS__" Foreground="#C9D1DC"
                   TextTrimming="CharacterEllipsis"/>
      </Grid>
      <StackPanel x:Name="AgentList"/>
      <Border Height="1" Background="#2EFFFFFF" Margin="0,6,0,6"/>
    </StackPanel>

    <!-- Background program section, same rules: collapsed unless the snapshot
         reports jobs, two lines per job, built in code into JobList. -->
    <StackPanel x:Name="JobsPanel" Grid.Row="4" Visibility="Collapsed" Margin="0,0,0,6">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" Text="后台" Margin="0,0,10,0"
                   FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
        <TextBlock x:Name="JobsSummary" Grid.Column="1" Text=""
                   FontFamily="__FF__" FontSize="__FS__" Foreground="#C9D1DC"
                   TextTrimming="CharacterEllipsis"/>
      </Grid>
      <StackPanel x:Name="JobList"/>
    </StackPanel>

    <Grid x:Name="Footer" Grid.Row="5">
      <!-- One column per field, and every numeric column is right-aligned, so
           the ￥ column, the $ column and the token column each end on a
           straight vertical edge on every row.  The label column is Chinese
           and the face is monospace, so the old padded-string footer could
           never line these up; the Grid does it without any padding.
             col0 = label (今日 / 峰谷 / 总计 / 余额)
             col1 = ￥ column, also carries the balance and the peak phase
             col2 = $ column
             col3 = token column, flush with the right edge of the panel     -->
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="Auto"/>
        <ColumnDefinition Width="Auto"/>
        <ColumnDefinition Width="Auto"/>
        <ColumnDefinition Width="*"/>
      </Grid.ColumnDefinitions>
      <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
      </Grid.RowDefinitions>

      <TextBlock Grid.Row="0" Grid.Column="0" Text="今日" Margin="0,0,10,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
      <TextBlock x:Name="TodayCny" Grid.Row="0" Grid.Column="1" Text="￥—" HorizontalAlignment="Left" Margin="0,0,12,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#F0D090"/>
      <TextBlock x:Name="TodayUsd" Grid.Row="0" Grid.Column="2" Text="$—" HorizontalAlignment="Left" Margin="0,0,12,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#A8B2C0"/>
      <StackPanel Grid.Row="0" Grid.Column="3" Orientation="Horizontal" HorizontalAlignment="Right">
        <TextBlock x:Name="TodayTok" Text="—" FontFamily="__FF__" FontSize="__FS__" Foreground="#8FD0B0"/>
        <TextBlock Text=" tok" FontFamily="__FF__" FontSize="__FS__" Foreground="#5F6874"/>
      </StackPanel>

      <TextBlock Grid.Row="1" Grid.Column="0" Text="峰谷" Margin="0,0,10,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
      <TextBlock x:Name="PeakText" Grid.Row="1" Grid.Column="1" Text="—" HorizontalAlignment="Left"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#8FD0B0"/>

      <TextBlock Grid.Row="2" Grid.Column="0" Text="总计" Margin="0,0,10,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
      <TextBlock x:Name="TotalCny" Grid.Row="2" Grid.Column="1" Text="￥—" HorizontalAlignment="Left" Margin="0,0,12,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#E6EAF2"/>
      <TextBlock x:Name="TotalUsd" Grid.Row="2" Grid.Column="2" Text="$—" HorizontalAlignment="Left" Margin="0,0,12,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#A8B2C0"/>

      <TextBlock Grid.Row="3" Grid.Column="0" Text="余额" Margin="0,0,10,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#8B93A1"/>
      <TextBlock x:Name="BalanceText" Grid.Row="3" Grid.Column="1" Text="—" HorizontalAlignment="Left" Margin="0,0,12,0"
                 FontFamily="__FF__" FontSize="__FS__" Foreground="#E8C07A"/>
    </Grid>
  </Grid>
</Border>
'@
$xaml = $xaml.Replace('__FF__', [string]$cfg.fontFamily).Replace('__FS__', [string]([double]$cfg.fontSize).ToString([System.Globalization.CultureInfo]::InvariantCulture))

$root = [System.Windows.Markup.XamlReader]::Parse($xaml)

$script:Window = New-Object System.Windows.Window
$script:Window.WindowStyle        = [System.Windows.WindowStyle]::None
$script:Window.AllowsTransparency = $true
$script:Window.Background         = [System.Windows.Media.Brushes]::Transparent
$script:Window.ShowInTaskbar      = $false
$script:Window.ResizeMode         = [System.Windows.ResizeMode]::NoResize
$script:Window.Topmost            = $true
$script:Window.ShowActivated      = $false
$script:Window.Focusable          = $false
$script:Window.SizeToContent      = [System.Windows.SizeToContent]::Height
# The window is one fixed-width column: the footer is a Grid, every toast is a
# single line, and the two status sections are shorter than a toast.  The
# widest realistic toast is now the timestamped one
#   '00:12:47 上传 未命中 4,500,000tokens -￥0.000002'
# which measures 27.09 em in the configured face (measured, Cascadia Code,
# 14 px -> 379.3 px; the old timestamp-less line was 21.8 em), so 27.2 em of
# content plus the 1 px border and the 10 px side padding keeps every line on
# one row.  Derived from fontSize, so a larger font never wraps or trims:
# 12 px -> 349 px, 14 px -> 403 px.
$script:Window.Width              = [math]::Ceiling($script:FontSize * 27.2) + 22
$script:Window.WindowStartupLocation = [System.Windows.WindowStartupLocation]::Manual
$script:Window.Opacity            = $script:WinOpacity
$script:Window.Title              = 'DSH usage'
$script:Window.Content            = $root

$ui = @{}
foreach ($n in @('ContentGrid', 'HintText', 'ToastPanel', 'Footer', 'TodayCny', 'TodayUsd', 'TodayTok', 'PeakText', 'TotalCny', 'TotalUsd', 'BalanceText',
                 'AgentsPanel', 'AgentsSummary', 'AgentList', 'JobsPanel', 'JobsSummary', 'JobList')) {
    $ui[$n] = $root.FindName($n)
}
$script:UI = $ui

# Toast / hint colours.  Only the two upload lines are coloured: 命中 green,
# 未命中 red.  Everything else - 下载 lines, engine messages, the dim hint, the
# separator and the whole footer - keeps the neutral colour it had.  Both
# accents are bright and desaturated enough to stay legible on the
# #F2181A1E panel at 86 % opacity over a light OR dark desktop.
$brushToast = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0xC9, 0xD1, 0xDC))
$brushDim   = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0x79, 0x81, 0x8C))
$brushHit   = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0x7E, 0xE7, 0x87))  # green
$brushMiss  = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0xFF, 0x7B, 0x72))  # red
$brushPeak  = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0xE8, 0xA1, 0x5C))
$brushOff   = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0x8F, 0xD0, 0xB0))
# The two status sections.  Running agents get their own soft green - close
# enough to 命中 green to read as "alive", distinct enough not to be mistaken
# for a token line; everything about a job stays neutral white/dim, and no job
# ever borrows the hit/miss accents.  All of them are light enough to survive
# 86 % opacity over a light or a dark desktop.
$brushAgentRun = New-Object System.Windows.Media.SolidColorBrush ([System.Windows.Media.Color]::FromRgb(0x93, 0xDD, 0xA0))  # soft green

# --------------------------------------------------------------------------
# 3. placement: the pet is anchored on its own, the panel follows the character
# --------------------------------------------------------------------------
# No cycle: the pet window is pinned to the WORK AREA's bottom-right corner and
# never looks at the panel; the panel then aligns its own right edge with the
# character's measured right edge, which the host publishes in pet\host\model.json
# (page bounds measured with PixiJS + an alpha scan, converted to screen px by the
# host from the window's real rect).
#
#   pet    : right = wa.Right - margin, bottom = wa.Bottom - margin, size petW x petH
#   panel  : right = model.screen.right            (== the character's right edge)
#            bottom = wa.Bottom - margin - petH/2 (unchanged pin: grows upwards)
#
# Until the measurement lands (the model needs ~6 s to load) the right edge falls
# back to `pet.right - inset`, using the documented measured inset, so the panel
# does not visibly jump when the real number arrives.
#
# The clamps keep the panel inside the work area on a monitor too small for it.
function Get-PetModelMetrics {
    # Read pet\host\model.json at most once a second; a document older than
    # ModelStaleMs is ignored (the host writes it every 1.5 s while it runs).
    $now = Get-Date
    if ($null -ne $script:PetModel -and ($now - $script:PetModelReadAt).TotalMilliseconds -lt 1000) { return $script:PetModel }
    $script:PetModelReadAt = $now
    $doc = $null
    try {
        if (Test-Path -LiteralPath $script:PetModelPath) {
            $raw = [IO.File]::ReadAllText($script:PetModelPath, (New-Object System.Text.UTF8Encoding($false)))
            $doc = $raw | ConvertFrom-Json
            $at = To-Num (Get-PropCI $doc 'at')
            if ($null -eq $at -or ((Get-EpochNowMs) - $at) -gt 15000) { $doc = $null }
        }
    } catch { $doc = $null }
    $script:PetModel = $doc
    return $doc
}

function Get-WidgetPlacement {
    $wa = [System.Windows.SystemParameters]::WorkArea
    $w = $script:Window.ActualWidth;  if ($w -le 0) { $w = $script:Window.Width }
    $h = $script:Window.ActualHeight; if ($h -le 0) { $h = 120 }
    # The pet's space is always reserved: -NoPet only means "do not start or
    # supervise the host", so a panel-only -DevSnapshot still measures the
    # production layout (same corner, same panel bottom pin).
    $petW = $script:PetW; $petH = $script:PetH

    # the pet window: work area corner, independent of the panel
    $petX = $wa.Right  - $script:PetMarginX - $petW
    $petY = $wa.Bottom - $script:PetMarginY - $petH

    # the panel's right edge == the character's right edge (measured)
    $panelRight = $null
    $metrics = Get-PetModelMetrics
    if ($null -ne $metrics) {
        $mr = To-Num (Get-First $metrics @('screen.model.right'))
        if ($null -ne $mr) { $panelRight = [int][math]::Round($mr) }
    }
    if ($null -eq $panelRight) {
        # No measurement yet (the model needs ~6 s to load): the character's right
        # edge sits this many px inside the pet window's right edge.  The number is
        # measured for the shipped geometry (pet 340x340, fill 0.735, host
        # -ModelShiftX 16) and is what the host publishes as soon as it has
        # measured, so the panel does not visibly jump when the real value lands.
        $panelRight = $petX + $petW - $script:PetSilhouetteInsetPx
    }
    if ($panelRight -gt $wa.Right) { $panelRight = $wa.Right }
    # The panel's bottom rides on the pet geometry: the character's head top sits
    # 58 px below it (that was the accepted task-4 relation), so shifting the model
    # down inside its window (PetModelShiftY) moves the whole panel down with it -
    # which is what "整体往下" means.  The extra PetModelShiftY term is exactly that
    # relation, and it also means the footer text line above the label keeps its
    # 1 px distance from the head whatever the shift is.
    $panelBottom = $wa.Bottom - $script:PetMarginY - [math]::Ceiling($petH / 2) + $script:PetModelShiftY
    $panelLeft   = $panelRight - $w
    $panelTop    = $panelBottom - $h
    if ($panelLeft -lt $wa.Left) { $panelLeft = $wa.Left;  $panelRight  = $panelLeft + $w }
    if ($panelTop  -lt $wa.Top)  { $panelTop  = $wa.Top;   $panelBottom = $panelTop + $h }
    return [pscustomobject]@{
        PanelLeft   = [int][math]::Round($panelLeft)
        PanelTop    = [int][math]::Round($panelTop)
        PanelRight  = [int][math]::Round($panelRight)
        PanelBottom = [int][math]::Round($panelBottom)
        PetX        = [int][math]::Round($petX)
        PetY        = [int][math]::Round($petY)
        PetW        = [int]$petW
        PetH        = [int]$petH
        ModelRight  = $panelRight
        ModelSource = $(if ($null -ne $metrics) { 'measured' } else { 'default' })
    }
}

function Get-PetHwnd {
    # The pet host is a separate process with its own window, titled 'DSH pet'.
    # The handle is cached while the window lives and re-found after a restart.
    if ($script:PetHwnd -ne [IntPtr]::Zero -and [DshWin32]::IsWindowAlive($script:PetHwnd)) { return $script:PetHwnd }
    $script:PetHwnd = [IntPtr]::Zero
    if (-not $script:PetHostEnabled) { return $script:PetHwnd }
    if ($script:PetProc -and $script:PetProc.HasExited) { return $script:PetHwnd }
    try { $script:PetHwnd = [DshWin32]::FindWindowByTitle('DSH pet') } catch { $script:PetHwnd = [IntPtr]::Zero }
    return $script:PetHwnd
}

function Move-Pet {
    # Re-asserts topmost at the same time (SetWindowPos with HWND_TOPMOST), which
    # is the only way that actually does anything: assigning the WPF Topmost
    # property the value it already has is a no-op.
    param([int]$X, [int]$Y)
    if (-not $script:PetHostEnabled) { return }
    $h = Get-PetHwnd
    if ($h -eq [IntPtr]::Zero) { return }
    try { [void][DshWin32]::MoveTopmost($h, $X, $Y, $script:PetW, $script:PetH) } catch { }
}

function Update-Placement {
    $p = Get-WidgetPlacement
    $script:Window.Left = $p.PanelLeft
    $script:Window.Top  = $p.PanelTop
    if ($script:PetHostEnabled) { Move-Pet $p.PetX $p.PetY }
}

# --------------------------------------------------------------------------
# 3b. the pet host process (started, positioned, shown/hidden and stopped here)
# --------------------------------------------------------------------------
# One host for the life of the panel, exactly like the engine: the panel is the
# single entry point and the supervisor.  It is not restarted while it runs, it
# is hidden/shown with the panel, and it is stopped when the panel exits.
function Write-DshHeartbeat {
    # The engine reads this file to answer `dshRunning` for the pet's state
    # (engine/pet-state.mjs).  It is the same Get-Process observation the panel
    # itself uses to show or hide, so the pet's 离线 state and the panel's
    # visibility cannot disagree.  Never fatal: a heartbeat that cannot be
    # written simply ages out and the engine falls back to the snapshot.
    param([bool]$Running)
    try {
        $doc = [ordered]@{
            running = [bool]$Running
            pid     = $PID
            at      = [int64](Get-EpochNowMs)
        }
        Set-Content -LiteralPath $script:DshHeartbeatFile -Value ($doc | ConvertTo-Json -Compress) -Encoding ASCII
    } catch { }
}

function Start-Pet {
    if (-not $script:PetHostEnabled) { return }
    if ($script:Exiting) { return }
    if ($script:PetProc -and (-not $script:PetProc.HasExited)) { return }
    if ((Get-Date) -lt $script:PetNextStart) { return }
    $script:PetNextStart = (Get-Date).AddSeconds(30)   # a failed host is not retried in a hot loop

    if (-not (Test-Path -LiteralPath $script:PetHostPath)) {
        if (-not $script:PetWarned) {
            $script:PetWarned = $true
            Add-Toast -Text ('桌宠宿主不存在: ' + $script:PetHostPath) -Dim
        }
        return
    }
    $p = Get-WidgetPlacement
    # The stop file is per panel: clear it before the host starts, so a file left
    # behind by a previous run cannot kill the new host.
    try { if (Test-Path -LiteralPath $script:PetStopFile) { Remove-Item -LiteralPath $script:PetStopFile -Force } } catch { }

    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName        = 'powershell.exe'
        $psi.Arguments       = '-NoProfile -File "' + $script:PetHostPath + '"' +
                               ' -X ' + $p.PetX + ' -Y ' + $p.PetY +
                               ' -W ' + $script:PetW + ' -H ' + $script:PetH +
                               ' -ParentPid ' + $PID +
                               ' -StopFile "' + $script:PetStopFile + '"' +
                               ' -AnchorBr -Fill ' + $script:PetFill.ToString([System.Globalization.CultureInfo]::InvariantCulture) +
                               ' -ModelShiftX ' + $script:PetModelShiftX + ' -ModelShiftY ' + $script:PetModelShiftY
        $psi.WorkingDirectory = $script:RootDir
        $psi.UseShellExecute  = $false
        $psi.CreateNoWindow   = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        $script:PetProc = $proc
        $script:PetHwnd = [IntPtr]::Zero
        # The host shows its own window (it has to, to load WebView2), so the new
        # window counts as VISIBLE here even when the panel is hidden.  The next
        # pet tick (<= 1.5 s) hides it again; an empty WebView2 window shows
        # nothing in that window anyway (the model needs ~8 s to load), and the
        # alternative - never starting the host while hidden - would make the pet
        # appear 8 s after DSH comes back instead of being ready for it.
        $script:PetVisible = $true
    }
    catch {
        if (-not $script:PetWarned) {
            $script:PetWarned = $true
            Add-Toast -Text ('桌宠启动失败: ' + $_.Exception.Message) -Dim
        }
    }
}

function Sync-PetVisibility {
    # The pet follows the panel: when DSH is not running the panel hides itself
    # and the pet must hide with it (and come back with it).
    if (-not $script:PetHostEnabled) { return }
    $h = Get-PetHwnd
    if ($h -eq [IntPtr]::Zero) { return }
    $want = [bool]$script:Window.IsVisible
    if ($want -eq $script:PetVisible) { return }
    $script:PetVisible = $want
    try {
        if ($want) { [void][DshWin32]::ShowWindowNoActivate($h, [DshWin32]::SW_SHOWNOACTIVATE) }
        else       { [void][DshWin32]::ShowWindowNoActivate($h, [DshWin32]::SW_HIDE) }
    } catch { }
}

function Publish-PetGeometry {
    # The page cannot see the panel, so the panel hands it the two anchors the
    # status label needs, MEASURED from its own live layout and expressed in the
    # pet page's CSS px (the page's viewport origin = the pet window's origin):
    #
    #   labelRightPage = the right edge of the panel's right-aligned text
    #                    (the content Grid's right edge - where 321.8M tok and the
    #                    job progress values end), minus the pet window's x
    #   labelTopPage   = the bottom edge of the panel text line above the label
    #                    (TodayTok, the footer's token cell) + PetLabelGapY,
    #                    minus the pet window's y
    #
    # Nothing here is a hard-coded x/y: both come from WPF layout, so a change of
    # padding, font or panel position flows through.  The page clamps them against
    # the measured character box (labelTop >= modelTop, labelRight <= modelRight).
    if ($script:Exiting) { return }
    $grid = $script:UI.ContentGrid
    $tok = $script:UI.TodayTok
    if ($null -eq $grid -or $null -eq $tok) { return }
    if (-not $script:Window.IsVisible) { return }
    if ($grid.ActualWidth -le 0 -or $tok.ActualHeight -le 0) { return }
    $p = Get-WidgetPlacement
    $contentRight = $null; $tokBottom = $null
    try {
        $g = $grid.TransformToAncestor($script:Window).Transform((New-Object System.Windows.Point($grid.ActualWidth, 0)))
        $contentRight = $script:Window.Left + $g.X
        $t = $tok.TransformToAncestor($script:Window).Transform((New-Object System.Windows.Point(0, $tok.ActualHeight)))
        $tokBottom = $script:Window.Top + $t.Y
    } catch { return }
    if ($null -eq $contentRight -or $null -eq $tokBottom) { return }
    # The panel's own bottom edge, in page px: the page's reaction layer puts the
    # speech bubble BELOW it, so the bubble can never cover panel text (the whole
    # panel sits above this line).
    $panelBottom = $script:Window.Top + $script:Window.ActualHeight
    $doc = [ordered]@{
        at              = [int64](Get-EpochNowMs)
        labelRightPage  = [math]::Round($contentRight - $p.PetX, 1)
        labelTopPage    = [math]::Round($tokBottom + $script:PetLabelGapY - $p.PetY, 1)
        gapY            = $script:PetLabelGapY
        contentRight    = [int][math]::Round($contentRight)
        textBottom      = [int][math]::Round($tokBottom)
        panelBottomPage = [int][math]::Round($panelBottom - $p.PetY)
        window          = [ordered]@{ x = $p.PetX; y = $p.PetY; width = $p.PetW; height = $p.PetH }
    }
    $text = $doc | ConvertTo-Json -Depth 4 -Compress
    if ($text -eq $script:PetGeometryText) { return }
    $script:PetGeometryText = $text
    try {
        $tmp = $script:PetGeometryPath + '.tmp'
        [IO.File]::WriteAllText($tmp, $text, (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $tmp -Destination $script:PetGeometryPath -Force
    } catch { }
}

function Stop-Pet {
    # Ask the host to leave (it closes WebView2 and its browser processes), give
    # it a moment, then make sure.  Called on panel exit only.
    if (-not $script:PetHostEnabled) { return }
    $proc = $script:PetProc
    $script:PetProc = $null
    $script:PetHwnd = [IntPtr]::Zero
    $script:PetVisible = $false
    try { Set-Content -LiteralPath $script:PetStopFile -Value 'stop' -Encoding ASCII } catch { }
    if ($null -ne $proc) {
        try { [void]$proc.WaitForExit(3000) } catch { }
        try { if (-not $proc.HasExited) { $proc.Kill() } } catch { }
        try { [void]$proc.WaitForExit(2000) } catch { }
        try { $proc.Dispose() } catch { }
    }
}

function Invoke-PetTick {
    # 1.5 s cadence, deliberately faster than the panel's own 2 s topmost
    # re-assertion so the pet wins the tie where the two windows overlap, without
    # either of them fighting forever (see the brief's requirement 5).
    if ($script:Exiting) { return }
    # The label anchors are published for the page even when this instance does
    # not own a host (-NoPet), so a panel-only development run still describes the
    # production layout.
    Publish-PetGeometry
    if (-not $script:PetHostEnabled) { return }
    Start-Pet
    $h = Get-PetHwnd
    if ($h -eq [IntPtr]::Zero) { return }
    $p = Get-WidgetPlacement
    if ([DshWin32]::IsWindowAlive($h)) { Move-Pet $p.PetX $p.PetY } else { return }
    Sync-PetVisibility
}

$script:Toasts = New-Object System.Collections.ArrayList

function Add-Toast {
    # $Kind picks the colour of a line that carries a meaning: 'hit' (上传 命中)
    # is green, 'miss' (上传 未命中) is red.  Everything else - 下载 lines,
    # engine messages, the dim hint - keeps the neutral white / dim colour.
    param([string]$Text, [switch]$Dim, [string]$Kind = 'normal')
    $tb = New-Object System.Windows.Controls.TextBlock
    $tb.Text = $Text
    $tb.FontFamily = $script:FontFamily
    $tb.FontSize = $script:FontSize
    $tb.TextTrimming = [System.Windows.TextTrimming]::CharacterEllipsis
    if ($Dim)                 { $tb.Foreground = $brushDim }
    elseif ($Kind -eq 'hit')  { $tb.Foreground = $brushHit }
    elseif ($Kind -eq 'miss') { $tb.Foreground = $brushMiss }
    else                      { $tb.Foreground = $brushToast }
    [void]$script:UI.ToastPanel.Children.Add($tb)
    $rec = @{ El = $tb; Born = [datetime]::UtcNow }
    [void]$script:Toasts.Add($rec)
    # A history, not a notification queue: up to toastMax lines exist at once
    # and the moment a newer one arrives the oldest is dropped.  No per-toast
    # timer and no opacity animation is involved anywhere.
    while ($script:UI.ToastPanel.Children.Count -gt $script:ToastMax) {
        $oldest = $script:UI.ToastPanel.Children[0]
        $script:UI.ToastPanel.Children.RemoveAt(0)
        for ($i = 0; $i -lt $script:Toasts.Count; $i++) {
            if ([object]::ReferenceEquals($script:Toasts[$i].El, $oldest)) { $script:Toasts.RemoveAt($i); break }
        }
    }
    Update-Placement
}

function Update-Toasts {
    # Nothing fades any more and nothing animates.  toastLifeMs = 0 means a line
    # never expires: it stays until a newer line pushes it out of the history.
    # A positive toastLifeMs is the only way a line ever leaves on its own, and
    # even then it leaves instantly.
    if ($script:ToastLifeMs -le 0) { return }
    if ($script:Toasts.Count -eq 0) { return }
    $now = [datetime]::UtcNow
    for ($i = $script:Toasts.Count - 1; $i -ge 0; $i--) {
        $rec = $script:Toasts[$i]
        if (($now - $rec.Born).TotalMilliseconds -ge $script:ToastLifeMs) {
            [void]$script:UI.ToastPanel.Children.Remove($rec.El)
            $script:Toasts.RemoveAt($i)
            Update-Placement
        }
    }
}

# --------------------------------------------------------------------------
# 4. footer
# --------------------------------------------------------------------------
function Set-Connected {
    param([bool]$Connected, [string]$Reason)
    $script:EngineConnected = $Connected
    if ($Connected) { $script:UI.HintText.Visibility = [System.Windows.Visibility]::Collapsed }
    else {
        $script:UI.HintText.Visibility = [System.Windows.Visibility]::Visible
        # a disconnected engine owns no agents and no jobs any more
        Reset-StatusSections
    }
}

function Reset-Footer {
    $script:UI.TodayCny.Text = '￥—'
    $script:UI.TodayUsd.Text = '$—'
    $script:UI.TodayTok.Text = '—'
    $script:UI.TotalCny.Text = '￥—'
    $script:UI.TotalUsd.Text = '$—'
    $script:UI.BalanceText.Text = '—'
}

function Update-PeakLine {
    $utc = [datetime]::UtcNow
    $peak = Test-PeakHour $utc
    if ($peak) {
        if ($script:UI.PeakText.Text -ne '峰时') { $script:UI.PeakText.Text = '峰时' }
        $script:UI.PeakText.Foreground = $brushPeak
    }
    else {
        if ($script:UI.PeakText.Text -ne '谷时') { $script:UI.PeakText.Text = '谷时' }
        $script:UI.PeakText.Foreground = $brushOff
    }
}

function Update-Footer {
    param($o)
    $src = Get-Payload $o @('todayCny', 'todayCostCny', 'costCnyToday', 'today.cny', 'totalCny', 'totalCostCny', 'balanceCny', 'balance')

    $todayCny = To-Num (Get-First $src @('todayCny', 'todayCostCny', 'costCnyToday', 'todayCNY', 'costTodayCny', 'today.cny', 'today.costCny', 'today.cost_cny', 'today.cost'))
    $todayUsd = To-Num (Get-First $src @('todayUsd', 'todayCostUsd', 'costUsdToday', 'todayUSD', 'costTodayUsd', 'today.usd', 'today.costUsd', 'today.cost_usd'))
    $todayTok = To-TokenCount (Get-First $src @('todayTokens', 'tokensToday', 'today.totalTokens', 'today.tokens', 'today.tokens.total'))
    $totalCny = To-Num (Get-First $src @('totalCny', 'totalCostCny', 'costCnyTotal', 'totalCNY', 'allTimeCny', 'total.cny', 'total.costCny', 'total.cost_cny', 'total.cost'))
    $totalUsd = To-Num (Get-First $src @('totalUsd', 'totalCostUsd', 'costUsdTotal', 'totalUSD', 'allTimeUsd', 'total.usd', 'total.costUsd', 'total.cost_usd'))

    # engine/cli.mjs: "balance":{"ok":true,"currency":"CNY","total":"8.47",...}
    $balRaw = Get-First $src @('balance.total', 'balanceCny', 'balanceCNY', 'balance.totalCny', 'balance.amount', 'balance_cny', 'account.balance', 'balance')
    $balOk  = Get-First $src @('balance.ok', 'balanceOk', 'balance.valid', 'ok')
    $balCur = Get-First $src @('balance.currency', 'currency')
    $balErr = Get-First $src @('balance.error', 'balance.message')

    if ($null -ne $todayCny) { $script:UI.TodayCny.Text = Format-Cny $todayCny }
    if ($null -ne $todayUsd) { $script:UI.TodayUsd.Text = Format-Usd $todayUsd }
    if ($null -ne $todayTok) { $script:UI.TodayTok.Text = Format-Tokens $todayTok }
    if ($null -ne $totalCny) { $script:UI.TotalCny.Text = Format-Cny $totalCny }
    if ($null -ne $totalUsd) { $script:UI.TotalUsd.Text = Format-Usd $totalUsd }

    if ($balOk -is [bool] -and (-not $balOk)) {
        $script:UI.BalanceText.Text = '—'          # engine said ok:false
        if ($balErr -is [string]) { $script:UI.BalanceText.ToolTip = $balErr } else { $script:UI.BalanceText.ToolTip = 'balance unavailable' }
    }
    elseif ($null -ne $balRaw) {
        if ($balRaw -is [string]) {
            # "shown exactly as the engine reports it": the amount is a bare CNY
            # string ("8.47"), so the ￥ sign is added by the UI.
            $s = $balRaw.Trim()
            $sym = '￥'
            if ($balCur -is [string] -and $balCur.Length -gt 0 -and ($balCur -ine 'CNY')) { $sym = '' }
            if ($s -match '^[0-9]') { $s = $sym + $s }
            $script:UI.BalanceText.Text = $s
        }
        else {
            $n = To-Num $balRaw
            if ($null -ne $n) { $script:UI.BalanceText.Text = ('￥{0:0.00}' -f $n) }
        }
        $script:UI.BalanceText.ToolTip = $null
    }
}

# --------------------------------------------------------------------------
# 4b. agent + background program sections
# --------------------------------------------------------------------------
# Both sections are driven by the LAST snapshot alone.  "key missing" and
# "key present but []" are the same thing here: draw nothing - no row, no
# summary, and for the agents no leftover separator rule either (the rule is a
# child of the panel, so hiding the panel hides the rule).
#
# Rows are rebuilt only when something they display actually changes.  A
# snapshot arrives every pollMs and the elapsed counters tick with it, so the
# signature below deliberately rounds the elapsed time down to whole seconds -
# that is the resolution the row prints - and nothing is rebuilt in between.

$script:AgentsSig = ''
$script:JobsSig   = ''

function Get-ElapsedMs($rec) {
    # elapsedMs when the engine sends it; otherwise measured from startedAt.
    $ms = To-Num (Get-First $rec @('elapsedMs', 'elapsed_ms', 'elapsed', 'runtimeMs'))
    if ($null -eq $ms) {
        $started = To-Num (Get-First $rec @('startedAt', 'started_at', 'start', 'startedMs'))
        if ($null -ne $started -and (Test-EpochMs $started)) { $ms = (Get-EpochNowMs) - $started }
    }
    if ($null -eq $ms -or [double]::IsNaN($ms) -or $ms -lt 0) { $ms = 0 }
    return $ms
}

function Get-JobProgressText($job) {
    # "45.2%  剩余 00:37" from a progress object; otherwise the engine's note,
    # otherwise 进度未知.  Half a progress object (percent without ETA or the
    # other way round) prints the half it has.
    $prog = Get-First $job @('progress')
    $pct = $null; $eta = $null
    if ($null -ne $prog -and -not ($prog -is [string])) {
        $pct = To-Num (Get-First $prog @('percent', 'pct', 'percentage'))
        $eta = To-Num (Get-First $prog @('etaMs', 'eta_ms', 'eta', 'remainingMs'))
    }
    if ($null -ne $eta -and $eta -lt 0) { $eta = $null }

    $parts = @()
    if ($null -ne $pct) { $parts += ('{0:0.0}%' -f $pct) }
    if ($null -ne $eta) { $parts += ('剩余 ' + (Format-Duration $eta)) }
    if ($parts.Count -eq 0) {
        $note = [string](Get-First $job @('progressNote', 'progress_note', 'note'))
        if (-not [string]::IsNullOrWhiteSpace($note)) { $parts += $note.Trim() }
        else { $parts += '进度未知' }
    }
    return ($parts -join '  ')
}

function New-StatusText {
    # Every line in both sections is one of these: monospace, no wrap, and an
    # ellipsis instead of a second row when the text does not fit.
    param([string]$Text, $Brush, [switch]$Trim, [switch]$Right)
    $tb = New-Object System.Windows.Controls.TextBlock
    $tb.Text = $Text
    $tb.FontFamily = $script:FontFamily
    $tb.FontSize = $script:FontSize
    $tb.Foreground = $Brush
    $tb.TextWrapping = [System.Windows.TextWrapping]::NoWrap
    if ($Trim)  { $tb.TextTrimming = [System.Windows.TextTrimming]::CharacterEllipsis }
    if ($Right) { $tb.HorizontalAlignment = [System.Windows.HorizontalAlignment]::Right }
    return $tb
}

function New-AgentRow($agent) {
    #   ▸ <label, ellipsised>            <MM:SS>
    # Running green, everything else dim.  The label owns a star column and is
    # trimmed by WPF, so a long name can never wrap and can never push the time
    # off the panel.
    $state   = [string](Get-First $agent @('state', 'status'))
    $running = ($state -ieq 'running')
    $brush   = $(if ($running) { $brushAgentRun } else { $brushDim })
    $label   = [string](Get-First $agent @('label', 'title', 'name', 'id'))
    if ([string]::IsNullOrWhiteSpace($label)) { $label = '智能体' }

    $g = New-Object System.Windows.Controls.Grid
    $c0 = New-Object System.Windows.Controls.ColumnDefinition; $c0.Width = [System.Windows.GridLength]::Auto
    $c1 = New-Object System.Windows.Controls.ColumnDefinition; $c1.Width = [System.Windows.GridLength]::new(1.0, [System.Windows.GridUnitType]::Star)
    $c2 = New-Object System.Windows.Controls.ColumnDefinition; $c2.Width = [System.Windows.GridLength]::Auto
    [void]$g.ColumnDefinitions.Add($c0)
    [void]$g.ColumnDefinitions.Add($c1)
    [void]$g.ColumnDefinitions.Add($c2)

    $mark = New-StatusText -Text '  ▸ ' -Brush $brush
    [System.Windows.Controls.Grid]::SetColumn($mark, 0)
    [void]$g.Children.Add($mark)

    $name = New-StatusText -Text $label -Brush $brush -Trim
    $name.Margin = New-Object System.Windows.Thickness(0, 0, 10, 0)
    [System.Windows.Controls.Grid]::SetColumn($name, 1)
    [void]$g.Children.Add($name)

    $time = New-StatusText -Text (Format-Duration (Get-ElapsedMs $agent)) -Brush $brush -Right
    [System.Windows.Controls.Grid]::SetColumn($time, 2)
    [void]$g.Children.Add($time)
    return $g
}

function New-JobRow($job, [bool]$First) {
    #   ▶ pwsh  01:05              45.2%  剩余 00:37
    #     node sim.mjs --steps 500
    # The percentage / ETA block is right-aligned in the star column, so two
    # jobs' numbers land on the same edge no matter how long the program name
    # or the elapsed time is.  Neutral white for the first line, dim for the
    # command: no job ever borrows the 命中 / 未命中 colours.
    $program = [string](Get-First $job @('program', 'name', 'shell', 'tool'))
    if ([string]::IsNullOrWhiteSpace($program)) { $program = '程序' }
    $progress = Get-JobProgressText $job

    $g = New-Object System.Windows.Controls.Grid
    $c0 = New-Object System.Windows.Controls.ColumnDefinition; $c0.Width = [System.Windows.GridLength]::Auto
    $c1 = New-Object System.Windows.Controls.ColumnDefinition; $c1.Width = [System.Windows.GridLength]::Auto
    $c2 = New-Object System.Windows.Controls.ColumnDefinition; $c2.Width = [System.Windows.GridLength]::Auto
    $c3 = New-Object System.Windows.Controls.ColumnDefinition; $c3.Width = [System.Windows.GridLength]::new(1.0, [System.Windows.GridUnitType]::Star)
    [void]$g.ColumnDefinitions.Add($c0)
    [void]$g.ColumnDefinitions.Add($c1)
    [void]$g.ColumnDefinitions.Add($c2)
    [void]$g.ColumnDefinitions.Add($c3)

    $mark = New-StatusText -Text '  ▶ ' -Brush $brushToast
    [System.Windows.Controls.Grid]::SetColumn($mark, 0)
    [void]$g.Children.Add($mark)

    # a minimum width on the program column keeps the elapsed column from
    # drifting sideways between rows (6 monospace characters at this font size)
    $progBox = New-StatusText -Text $program -Brush $brushToast
    $progBox.MinWidth = [math]::Round($script:FontSize * 3.6)
    [System.Windows.Controls.Grid]::SetColumn($progBox, 1)
    [void]$g.Children.Add($progBox)

    $elapsed = New-StatusText -Text (Format-Duration (Get-ElapsedMs $job)) -Brush $brushToast
    $elapsed.Margin = New-Object System.Windows.Thickness(12, 0, 0, 0)
    [System.Windows.Controls.Grid]::SetColumn($elapsed, 2)
    [void]$g.Children.Add($elapsed)

    $right = New-StatusText -Text $progress -Brush $brushToast -Right
    [System.Windows.Controls.Grid]::SetColumn($right, 3)
    [void]$g.Children.Add($right)

    $stack = New-Object System.Windows.Controls.StackPanel
    [void]$stack.Children.Add($g)

    $cmd = [string](Get-First $job @('command', 'cmd', 'args', 'commandLine'))
    if ([string]::IsNullOrWhiteSpace($cmd)) { $cmd = [string](Get-First $job @('id')) }
    if (-not [string]::IsNullOrWhiteSpace($cmd)) {
        $line2 = New-StatusText -Text ('    ' + $cmd.Trim()) -Brush $brushDim -Trim
        [void]$stack.Children.Add($line2)
    }
    if (-not $First) { $stack.Margin = New-Object System.Windows.Thickness(0, 2, 0, 0) }
    return $stack
}

function Hide-AgentSection {
    if ($script:AgentsSig -eq '' -and $script:UI.AgentsPanel.Visibility -eq [System.Windows.Visibility]::Collapsed) { return }
    $script:AgentsSig = ''
    $script:UI.AgentsSummary.Text = ''
    $script:UI.AgentList.Children.Clear()
    $script:UI.AgentsPanel.Visibility = [System.Windows.Visibility]::Collapsed
    Update-Placement
}

function Hide-JobSection {
    if ($script:JobsSig -eq '' -and $script:UI.JobsPanel.Visibility -eq [System.Windows.Visibility]::Collapsed) { return }
    $script:JobsSig = ''
    # NOTE: this read `$script:JobsSummary.Text` (no `UI.`) and that one missing
    # qualifier killed the whole panel: PowerShell evaluated `$null.Text = ''`,
    # which is a terminating error, and the throw came out of the 80 ms pump
    # timer -> Dispatcher.Run -> the process exited (exit code 1, no message).
    # It only fired when the jobs section went from visible to empty, i.e. every
    # time the last background program finished - which is why the panel used to
    # disappear at apparently random moments.  Keep the `UI.` qualifier.
    $script:UI.JobsSummary.Text = ''
    $script:UI.JobList.Children.Clear()
    $script:UI.JobsPanel.Visibility = [System.Windows.Visibility]::Collapsed
    Update-Placement
}

function Update-AgentSection($o) {
    # A string or a nested array where an agent object belongs would render as a
    # row full of fallbacks; drop those instead of drawing them.
    $agents = @(Get-ArrayField $o @('agents', 'agentList', 'smartAgents', 'subagents') |
                Where-Object { $null -ne $_ -and ($_ -isnot [string]) -and ($_ -isnot [System.Array]) })
    if ($agents.Count -eq 0) { Hide-AgentSection; return }

    $running = @($agents | Where-Object { ([string](Get-First $_ @('state', 'status'))) -ieq 'running' })
    $idle    = @($agents | Where-Object { ([string](Get-First $_ @('state', 'status'))) -ine 'running' })
    # running first, snapshot order kept inside each group
    $ordered = @($running) + @($idle)
    $shown   = @($ordered | Select-Object -First $script:AgentsMax)

    $parts = @()
    if ($running.Count -gt 0) { $parts += ('' + $running.Count + ' 运行中') }
    if ($idle.Count -gt 0)    { $parts += ('' + $idle.Count + ' 空闲') }
    if ($parts.Count -eq 0)   { $parts += ('' + $agents.Count + ' 智能体') }
    $summary = $parts -join ' · '
    if ($agents.Count -gt $script:AgentsMax) { $summary += (' · +' + ($agents.Count - $script:AgentsMax)) }

    $sig = @('n=' + $agents.Count, 's=' + $summary) -join '|'
    foreach ($a in $shown) {
        $sig += ('#' + [string](Get-First $a @('state', 'status')) + '|' +
                 [string](Get-First $a @('label', 'title', 'name', 'id')) + '|' +
                 [string][math]::Floor((Get-ElapsedMs $a) / 1000))
    }
    if ($sig -eq $script:AgentsSig) { return }
    $script:AgentsSig = $sig

    $script:UI.AgentsSummary.Text = $summary
    $script:UI.AgentList.Children.Clear()
    foreach ($a in $shown) { [void]$script:UI.AgentList.Children.Add((New-AgentRow $a)) }
    $script:UI.AgentsPanel.Visibility = [System.Windows.Visibility]::Visible
    Update-Placement
}

function Update-JobSection($o) {
    $jobs = @(Get-ArrayField $o @('jobs', 'backgroundJobs', 'programs') |
              Where-Object { $null -ne $_ -and ($_ -isnot [string]) -and ($_ -isnot [System.Array]) })
    if ($jobs.Count -eq 0) { Hide-JobSection; return }

    $summary = ('' + $jobs.Count + ' 个程序运行中')
    $shown   = @($jobs | Select-Object -First $script:JobsMax)

    $sig = 'n=' + $jobs.Count
    foreach ($j in $shown) {
        $sig += ('#' + [string](Get-First $j @('program', 'name', 'shell', 'tool')) + '|' +
                 [string][math]::Floor((Get-ElapsedMs $j) / 1000) + '|' +
                 (Get-JobProgressText $j) + '|' +
                 [string](Get-First $j @('command', 'cmd', 'args', 'commandLine')))
    }
    if ($sig -eq $script:JobsSig) { return }
    $script:JobsSig = $sig

    $script:UI.JobsSummary.Text = $summary
    $script:UI.JobList.Children.Clear()
    $i = 0
    foreach ($j in $shown) {
        [void]$script:UI.JobList.Children.Add((New-JobRow $j ($i -eq 0)))
        $i++
    }
    $script:UI.JobsPanel.Visibility = [System.Windows.Visibility]::Visible
    Update-Placement
}

function Update-StatusSections($o) {
    Update-AgentSection $o
    Update-JobSection $o
}

function Reset-StatusSections {
    # The engine is gone: its agent list and job list go with it, so nothing on
    # screen claims that something is still running.
    Hide-AgentSection
    Hide-JobSection
}

# --------------------------------------------------------------------------
# 5. engine child process (asynchronous, never blocks the UI thread)
# --------------------------------------------------------------------------
$script:Queue          = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()
$script:EngineProc     = $null
$script:EngineConnected = $false
$script:Exiting        = $false
$script:PollMs         = $null

function Stop-Engine {
    foreach ($sid in @('dshw.engine.out', 'dshw.engine.err', 'dshw.engine.exit')) {
        try { Unregister-Event -SourceIdentifier $sid -ErrorAction SilentlyContinue } catch { }
        try { Get-Job -Name $sid -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue } catch { }
    }
    if ($script:EngineProc) {
        $p = $script:EngineProc
        $script:EngineProc = $null
        try { if (-not $p.HasExited) { $p.Kill() } } catch { }
        try { [void]$p.WaitForExit(2000) } catch { }
        try { $p.Dispose() } catch { }
    }
}

function Start-Engine {
    if ($script:Exiting) { return }
    if ($script:EngineProc -and (-not $script:EngineProc.HasExited)) { return }
    Stop-Engine

    if (-not (Test-Path -LiteralPath $script:EnginePath)) {
        Set-Connected $false 'missing'
        Reset-Footer
        Start-RetryTimer
        return
    }
    # a bare command name ("node") is resolved through PATH by CreateProcess
    $nodeExists = (Test-Path -LiteralPath $script:NodePath) -or ($script:NodePath -notmatch '[\\/]')
    if (-not $nodeExists) {
        Set-Connected $false 'no-node'
        Reset-Footer
        Start-RetryTimer
        return
    }

    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = $script:NodePath
        $psi.Arguments              = '"' + $script:EnginePath + '"'
        $psi.WorkingDirectory       = $script:RootDir
        $psi.UseShellExecute        = $false
        $psi.CreateNoWindow         = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8

        $p = New-Object System.Diagnostics.Process
        $p.StartInfo = $psi
        $p.EnableRaisingEvents = $true

        $md = @{ Q = $script:Queue }
        # The event actions run on a background runspace: they only push raw
        # lines into the ConcurrentQueue.  The UI thread drains it (section 6).
        Register-ObjectEvent -InputObject $p -EventName OutputDataReceived -SourceIdentifier 'dshw.engine.out' -MessageData $md -Action {
            if ($null -ne $Event.SourceEventArgs.Data) { $Event.MessageData.Q.Enqueue([string]$Event.SourceEventArgs.Data) }
        } | Out-Null
        Register-ObjectEvent -InputObject $p -EventName ErrorDataReceived -SourceIdentifier 'dshw.engine.err' -MessageData $md -Action {
            if ($null -ne $Event.SourceEventArgs.Data) { $Event.MessageData.Q.Enqueue('@@ERR ' + [string]$Event.SourceEventArgs.Data) }
        } | Out-Null
        Register-ObjectEvent -InputObject $p -EventName Exited -SourceIdentifier 'dshw.engine.exit' -MessageData $md -Action {
            $Event.MessageData.Q.Enqueue('@@EXIT ' + [string]$Event.SourceEventArgs.ExitCode)
        } | Out-Null

        [void]$p.Start()
        $p.BeginOutputReadLine()
        $p.BeginErrorReadLine()
        $script:EngineProc = $p
    }
    catch {
        Set-Connected $false 'start-failed'
        Reset-Footer
        Add-Toast -Text ('引擎启动失败: ' + $_.Exception.Message) -Dim
        Start-RetryTimer
    }
}

function Start-RetryTimer {
    if ($script:Exiting) { return }
    if ($script:RetryTimer) { $script:RetryTimer.Stop() }
    $script:RetryTimer = New-Object System.Windows.Threading.DispatcherTimer
    $script:RetryTimer.Interval = [TimeSpan]::FromSeconds(10)
    $script:RetryTimer.Add_Tick({
        $script:RetryTimer.Stop()
        if (-not $script:Exiting) { Start-Engine }
    })
    $script:RetryTimer.Start()
}

# --------------------------------------------------------------------------
# 6. engine line pump (UI thread) + JSON protocol
# --------------------------------------------------------------------------
function Push-EventToasts {
    param($o)
    $src = Get-Payload $o @('hit', 'hitTokens', 'cacheHit', 'miss', 'missTokens', 'out', 'outTokens', 'costCny')

    # The local clock stamp in front of every token line, from the event's `at`
    # (epoch milliseconds).  It is prepended to the same TextBlock, so the whole
    # line - stamp included - keeps the one colour the line already had, and a
    # line is never printed without a stamp: a missing or nonsensical `at`
    # falls back to the current local time.
    $atMs = To-Num (Get-First $o @('at', 'time', 'timestamp', 'ts', 'eventAt'))
    if ($null -eq $atMs) { $atMs = To-Num (Get-First $src @('at', 'timestamp', 'ts')) }
    if ($null -eq $atMs -or -not (Test-EpochMs $atMs)) { $atMs = Get-EpochNowMs }
    $stamp = Format-Clock $atMs

    $hit  = To-Num (Get-First $src @('hit', 'hitTokens', 'cacheHit', 'cacheHitTokens', 'inputHit', 'hit_tokens', 'promptCacheHitTokens'))
    $miss = To-Num (Get-First $src @('miss', 'missTokens', 'cacheMiss', 'cacheMissTokens', 'inputMiss', 'miss_tokens', 'promptCacheMissTokens'))
    $out  = To-Num (Get-First $src @('out', 'outTokens', 'output', 'outputTokens', 'completion', 'completionTokens', 'out_tokens'))
    $cost = To-Num (Get-First $src @('costCny', 'costCNY', 'cost_cny', 'cost.cny', 'cost'))

    if ($null -eq $hit)  { $hit = 0 }
    if ($null -eq $miss) { $miss = 0 }
    if ($null -eq $out)  { $out = 0 }
    if ($null -eq $cost) { $cost = 0 }

    $total = $hit + $miss + $out

    # ONE rule, used for every toast: the call's costCny is split across the
    # token categories in proportion to this call's token mix
    # (share_i = tokens_i / (hit + miss + out)).  Zero-token categories never
    # produce a toast, so their share is never displayed.
    $cats = @(
        @{ N = $hit;  K = 'hit';  T = '上传 命中 {0}tokens -￥{1}' },
        @{ N = $miss; K = 'miss'; T = '上传 未命中 {0}tokens -￥{1}' },
        @{ N = $out;  K = 'normal'; T = '下载 {0}tokens -￥{1}' }
    )
    foreach ($c in $cats) {
        if ($c.N -le 0) { continue }
        $share = 0.0
        if ($total -gt 0) { $share = [math]::Round($cost * ($c.N / $total), 6) }
        $text = $c.T -f (('{0:N0}' -f $c.N), (Format-Share $share))
        Add-Toast -Text ($stamp + ' ' + $text) -Kind $c.K
    }
}

function Pump-EngineLines {
    $item = $null
    $n = 0
    while ($script:Queue.TryDequeue([ref]$item)) {
        $line = [string]$item
        $n++
        if ($n -gt 500) { break }   # never let a flood starve the message loop

        if ($line.StartsWith('@@EXIT')) {
            $code = $line.Substring(6).Trim()
            if (-not $script:Exiting) {
                Set-Connected $false 'exited'
                Reset-Footer
                Add-Toast -Text ('引擎已退出 (' + $code + ')') -Dim
                Stop-Engine
                Start-RetryTimer
            }
            continue
        }
        if ($line.StartsWith('@@ERR')) {
            $errText = $line.Substring(5).Trim()
            if ($errText.Length -gt 0) { Add-Toast -Text $errText -Dim }
            continue
        }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $o = $null
        try { $o = $line | ConvertFrom-Json } catch { continue }   # non-JSON banner lines are ignored
        if ($null -eq $o) { continue }

        $type = [string](Get-First $o @('type', 'kind', 'event'))
        switch -Regex ($type) {
            '^(?i)snapshot$' {
                Update-Footer $o
                Update-StatusSections $o
                Set-Connected $true ''
            }
            '^(?i)event$' {
                Push-EventToasts $o
                Set-Connected $true ''
            }
            '^(?i)ready$' {
                $pm = To-Num (Get-First $o @('pollMs', 'poll_ms', 'intervalMs', 'interval'))
                if ($null -ne $pm) { $script:PollMs = $pm }
                if ($null -ne $script:UI.Footer) { $script:UI.Footer.ToolTip = ("engine ready (poll " + [string]$script:PollMs + " ms)") }
                Set-Connected $true ''
            }
            '^(?i)error$' {
                $msg = Get-First $o @('message', 'msg', 'error', 'text', 'detail')
                if ($null -eq $msg) { $msg = '引擎错误' }
                Add-Toast -Text ([string]$msg) -Dim
                Set-Connected $true ''
            }
            default {
                # unknown but snapshot-shaped payloads still refresh the footer
                if ($null -ne (Get-First $o @('todayCny', 'todayCostCny', 'totalCny', 'balanceCny'))) {
                    Update-Footer $o
                    Update-StatusSections $o
                    Set-Connected $true ''
                }
            }
        }
    }
}

# --------------------------------------------------------------------------
# 7. DSH presence watcher (the widget only shows alongside the app)
# --------------------------------------------------------------------------
function Test-DshRunning {
    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -ieq 'DeepSeek Harness' }
    return (@($procs).Count -gt 0)
}

function Apply-Visibility {
    param([bool]$DshRunning)
    if ($DshRunning -or $ForceShow) {
        if (-not $script:Window.IsVisible) {
            Update-Placement
            $script:Window.Topmost = $true
            $script:Window.Show()
            Update-Placement
        }
    }
    else {
        if ($script:Window.IsVisible) { $script:Window.Hide() }
    }
    # the pet is one more window of this panel: it hides and shows with it
    Sync-PetVisibility
}

# --------------------------------------------------------------------------
# 8. click-through (opt-in) + tray icon
# --------------------------------------------------------------------------
$script:ClickThrough = $false

function Get-WindowHandle {
    try { return (New-Object System.Windows.Interop.WindowInteropHelper($script:Window)).Handle }
    catch { return [IntPtr]::Zero }
}

function Set-ClickThrough {
    param([bool]$On)
    $h = Get-WindowHandle
    if ($h -eq [IntPtr]::Zero) { return }
    $style = [DshWin32]::GetExStyle($h)
    if ($On) {
        # WS_EX_TRANSPARENT | WS_EX_LAYERED -> the window ignores mouse input
        $style = $style -bor [DshWin32]::WS_EX_TRANSPARENT -bor [DshWin32]::WS_EX_LAYERED
    }
    else {
        $style = $style -band (-bnot [DshWin32]::WS_EX_TRANSPARENT)
    }
    [DshWin32]::SetExStyle($h, $style)
    $script:ClickThrough = $On
    if ($script:MenuItemClickThrough) {
        $script:MenuItemClickThrough.Text = $(if ($On) { '点击穿透：开' } else { '点击穿透：关' })
        $script:MenuItemClickThrough.Checked = $On
    }
    if ($On) { Add-Toast -Text '点击穿透已开启（用托盘图标关闭）' -Dim }
}

function Toggle-Visibility {
    if ($script:Window.IsVisible) { $script:Window.Hide() }
    else { Update-Placement; $script:Window.Topmost = $true; $script:Window.Show(); Update-Placement }
}

function Invoke-Exit {
    if ($script:Exiting) { return }
    $script:Exiting = $true
    try { $script:PumpTimer.Stop() } catch { }
    try { $script:DshTimer.Stop() } catch { }
    try { $script:PetTimer.Stop() } catch { }
    try { $script:RetryTimer.Stop() } catch { }
    if ($script:TrayIcon) {
        try { $script:TrayIcon.Visible = $false } catch { }
        try { $script:TrayIcon.Dispose() } catch { }
        $script:TrayIcon = $null
    }
    Stop-Pet
    Stop-Engine
    try { if ($script:Window) { $script:Window.Close() } } catch { }
    try { [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown() } catch { }
}

$script:TrayIcon = New-Object System.Windows.Forms.NotifyIcon
$script:TrayIcon.Icon = [System.Drawing.SystemIcons]::Application
$script:TrayIcon.Text = 'DSH 用量'

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$script:MenuItemClickThrough = New-Object System.Windows.Forms.ToolStripMenuItem
$script:MenuItemClickThrough.Text = '点击穿透：关'
$script:MenuItemClickThrough.CheckOnClick = $false
$script:MenuItemClickThrough.Add_Click({ Set-ClickThrough (-not $script:ClickThrough) })
$miShow = New-Object System.Windows.Forms.ToolStripMenuItem
$miShow.Text = '显示 / 隐藏'
$miShow.Add_Click({ Toggle-Visibility })
$miExit = New-Object System.Windows.Forms.ToolStripMenuItem
$miExit.Text = '退出'
$miExit.Add_Click({ Invoke-Exit })
[void]$menu.Items.Add($script:MenuItemClickThrough)
[void]$menu.Items.Add($miShow)
[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
[void]$menu.Items.Add($miExit)
$script:TrayIcon.ContextMenuStrip = $menu
$script:TrayIcon.Add_MouseClick({
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) { Toggle-Visibility }
})
$script:TrayIcon.Visible = $true

# --------------------------------------------------------------------------
# 9. window-level wiring, timers, run loop
# --------------------------------------------------------------------------
$script:Window.Add_SourceInitialized({
    # resident: never activate, never appear in alt-tab
    $h = (New-Object System.Windows.Interop.WindowInteropHelper($script:Window)).Handle
    if ($h -ne [IntPtr]::Zero) {
        $style = [DshWin32]::GetExStyle($h)
        $style = $style -bor [DshWin32]::WS_EX_NOACTIVATE -bor [DshWin32]::WS_EX_TOOLWINDOW
        [DshWin32]::SetExStyle($h, $style)
    }
    Update-Placement
})
$script:Window.Add_SizeChanged({ Update-Placement })
$script:Window.Add_Closed({
    if (-not $script:Exiting) {
        $script:Exiting = $true
        try { $script:PumpTimer.Stop() } catch { }
        try { $script:DshTimer.Stop() } catch { }
        try { $script:PetTimer.Stop() } catch { }
        try { $script:RetryTimer.Stop() } catch { }
        if ($script:TrayIcon) { try { $script:TrayIcon.Visible = $false; $script:TrayIcon.Dispose() } catch { } }
        Stop-Pet
        Stop-Engine
    }
    try { [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown() } catch { }
})

$script:PumpTimer = New-Object System.Windows.Threading.DispatcherTimer
$script:PumpTimer.Interval = [TimeSpan]::FromMilliseconds(80)
$script:PumpTimer.Add_Tick({
    Pump-EngineLines
    Update-Toasts
})

$script:DshTimer = New-Object System.Windows.Threading.DispatcherTimer
$script:DshTimer.Interval = [TimeSpan]::FromSeconds(2)
$script:DshTimer.Add_Tick({
    $running = Test-DshRunning
    # The pet's `dshRunning`, published for the engine: the same observation the
    # line below uses to show/hide, so the two can never disagree.
    Write-DshHeartbeat $running
    if ($running -ne $script:DshRunning) {
        $script:DshRunning = $running
        Apply-Visibility $running
    }
    elseif ($running) {
        $script:Window.Topmost = $true          # re-assert residency
        Update-Placement
    }
    Update-PeakLine
})

# The pet's own 1.5 s tick: keep the host alive, keep it positioned on the panel
# corner and on top, and keep it in step with the panel's visibility.  The tick
# is wrapped on purpose: a companion window must never take the panel down.
$script:PetTimer = New-Object System.Windows.Threading.DispatcherTimer
$script:PetTimer.Interval = [TimeSpan]::FromMilliseconds(1500)
$script:PetTimer.Add_Tick({ try { Invoke-PetTick } catch { } })

# ---- start everything -----------------------------------------------------
Reset-Footer
Update-PeakLine
Set-Connected $false 'starting'
Update-Placement

Start-Engine
$script:PumpTimer.Start()
$script:DshTimer.Start()
$script:PetTimer.Start()

$script:DshRunning = Test-DshRunning
Write-DshHeartbeat $script:DshRunning
Apply-Visibility $script:DshRunning
Update-Placement
Start-Pet

function Get-TextRectDump {
    # Every TextBlock in the live visual tree, with its REAL rect in screen px.
    # -DevSnapshot hands this out so the character's measured box can be
    # intersected with the text the panel actually draws: the check that the pet
    # covers no text (task-4).  The layout is the production layout, so the numbers
    # are the numbers the visible panel has.
    $rows = New-Object System.Collections.ArrayList
    $win = $script:Window
    function WalkText($el) {
        if ($null -eq $el) { return }
        if ($el -is [System.Windows.Controls.TextBlock]) {
            $t = [string]$el.Text
            if ($t.Trim().Length -gt 0 -and $el.ActualWidth -gt 0.5 -and $el.ActualHeight -gt 0.5) {
                try {
                    $pt = $el.TransformToAncestor($win).Transform((New-Object System.Windows.Point(0, 0)))
                    [void]$rows.Add([pscustomobject]@{
                        text = $t
                        x = [int][math]::Round($win.Left + $pt.X)
                        y = [int][math]::Round($win.Top + $pt.Y)
                        w = [int][math]::Ceiling($el.ActualWidth)
                        h = [int][math]::Ceiling($el.ActualHeight)
                    })
                } catch { }
            }
            return
        }
        if ($el -is [System.Windows.Controls.Panel]) { foreach ($c in $el.Children) { WalkText $c }; return }
        if ($el -is [System.Windows.Controls.Decorator]) { WalkText $el.Child; return }
        if ($el -is [System.Windows.Controls.ContentControl]) { WalkText $el.Content; return }
        if ($el -is [System.Windows.Controls.ItemsControl]) { foreach ($c in $el.Items) { WalkText $c }; return }
    }
    WalkText $win.Content
    return @($rows)
}

if ($DevSnapshot -and $DevSnapshotDelayMs -le 0) { $DevSnapshotDelayMs = 3000 }
if ($DevSnapshot) {
    $devTimer = New-Object System.Windows.Threading.DispatcherTimer
    $devTimer.Interval = [TimeSpan]::FromMilliseconds($DevSnapshotDelayMs)
    $devTimer.Add_Tick({
        $devTimer.Stop()
        try {
            if ($DevSnapshot) {
                $script:TextRectDump = Get-TextRectDump
                $lines = @()
                $lines += 'toastCount=' + $script:Toasts.Count + ' panelChildren=' + $script:UI.ToastPanel.Children.Count + ' max=' + $script:ToastMax
                foreach ($c in $script:UI.ToastPanel.Children) { $lines += ('  [' + $c.Text + '] opacity=' + $c.Opacity + ' colour=' + $c.Foreground.ToString()) }
                $lines += 'hint=' + $script:UI.HintText.Visibility
                $lines += 'footer=' + $script:UI.TodayCny.Text + '|' + $script:UI.TodayUsd.Text + '|' + $script:UI.TodayTok.Text + '|' + $script:UI.PeakText.Text + '|' + $script:UI.TotalCny.Text + '|' + $script:UI.TotalUsd.Text + '|' + $script:UI.BalanceText.Text
                $lines += 'agents=' + $script:UI.AgentsPanel.Visibility + ' summary=[' + $script:UI.AgentsSummary.Text + '] rows=' + $script:UI.AgentList.Children.Count + ' max=' + $script:AgentsMax
                foreach ($r in $script:UI.AgentList.Children) {
                    $cells = @()
                    foreach ($cel in $r.Children) { $cells += [string]$cel.Text }
                    $lines += ('  agent[' + ($cells -join '][') + '] colour=' + $r.Children[0].Foreground.ToString())
                }
                $lines += 'jobs=' + $script:UI.JobsPanel.Visibility + ' summary=[' + $script:UI.JobsSummary.Text + '] rows=' + $script:UI.JobList.Children.Count + ' max=' + $script:JobsMax
                foreach ($r in $script:UI.JobList.Children) {
                    foreach ($cel in $r.Children) {
                        if ($cel -is [System.Windows.Controls.Grid]) {
                            $cells = @()
                            foreach ($cel2 in $cel.Children) { $cells += [string]$cel2.Text }
                            $lines += ('  job[' + ($cells -join '][') + ']')
                        }
                        else { $lines += ('  job cmd[' + [string]$cel.Text + ']') }
                    }
                }
                $lines += 'window=' + $script:Window.ActualWidth + 'x' + $script:Window.ActualHeight + ' at ' + $script:Window.Left + ',' + $script:Window.Top + ' topmost=' + $script:Window.Topmost + ' opacity=' + $script:Window.Opacity + ' visible=' + $script:Window.IsVisible
                $pl = Get-WidgetPlacement
                $petHwndValue = Get-PetHwnd
                $lines += 'pet enabled=' + $script:PetHostEnabled + ' want=' + $pl.PetX + ',' + $pl.PetY + ' ' + $pl.PetW + 'x' + $pl.PetH +
                          ' panelRect=' + $pl.PanelLeft + ',' + $pl.PanelTop + ' ' + ($pl.PanelRight - $pl.PanelLeft) + 'x' + ($pl.PanelBottom - $pl.PanelTop) +
                          ' panelRight=' + $pl.PanelRight + ' modelRight=' + $pl.ModelRight + ' modelSource=' + $pl.ModelSource +
                          ' hwnd=0x' + ([int64]$petHwndValue).ToString('x') + ' visible=' + $script:PetVisible +
                          ' proc=' + $(if ($script:PetProc) { $script:PetProc.Id } else { 'none' })
                # Every TextBlock's real rect (screen px), so the character's box can
                # be intersected with the text the panel actually draws - the check
                # that the pet does not cover any text (task-4).
                $lines += 'textrects=' + $script:TextRectDump.Count + ' (screen px; window origin ' + $script:Window.Left + ',' + $script:Window.Top + ')'
                foreach ($tr in $script:TextRectDump) {
                    # note the parentheses: `-f` binds tighter than `+`, so
                    # '...' + $text + ']' -f $args would format only the ']'
                    $lines += ('  text x={0} y={1} w={2} h={3} right={4} bottom={5} [{6}]' -f `
                        $tr.x, $tr.y, $tr.w, $tr.h, ($tr.x + $tr.w), ($tr.y + $tr.h), $tr.text)
                }
                $mt = Get-PetModelMetrics
                if ($null -ne $mt) {
                    $lines += 'model.metrics screen.model=' + ((Get-First $mt @('screen.model')) | ConvertTo-Json -Compress) +
                              ' screen.label=' + ((Get-First $mt @('screen.label')) | ConvertTo-Json -Compress) +
                              ' gaps=' + ((Get-First $mt @('gaps')) | ConvertTo-Json -Compress)
                } else {
                    $lines += 'model.metrics (absent - host has not published pet\host\model.json yet)'
                }
                [System.IO.File]::WriteAllText($DevSnapshot + '.state.txt', ($lines -join "`r`n"))
            }
            if ($DevClickThrough -and $DevSnapshot) {
                # verification hook: prove the opt-in click-through really flips
                # the WS_EX_TRANSPARENT / WS_EX_LAYERED bits on the real window
                $hwnd = Get-WindowHandle
                $before = [DshWin32]::GetExStyle($hwnd)
                Set-ClickThrough $true
                $after = [DshWin32]::GetExStyle($hwnd)
                $txt = 'hwnd=0x{0:X} before=0x{1:X8} after=0x{2:X8} WS_EX_TRANSPARENT={3} WS_EX_LAYERED={4} WS_EX_NOACTIVATE={5} menutext={6} checked={7}' -f `
                    ([int64]$hwnd), $before, $after,
                    [bool]($after -band [DshWin32]::WS_EX_TRANSPARENT),
                    [bool]($after -band [DshWin32]::WS_EX_LAYERED),
                    [bool]($after -band [DshWin32]::WS_EX_NOACTIVATE),
                    $script:MenuItemClickThrough.Text, $script:MenuItemClickThrough.Checked
                [System.IO.File]::WriteAllText($DevSnapshot + '.style.txt', $txt)
            }
            $w = [int][math]::Ceiling($script:Window.ActualWidth)
            $h = [int][math]::Ceiling($script:Window.ActualHeight)
            if ($w -le 0) { $w = 288 }; if ($h -le 0) { $h = 120 }
            $rtb = New-Object System.Windows.Media.Imaging.RenderTargetBitmap($w, $h, 96, 96, [System.Windows.Media.PixelFormats]::Pbgra32)
            $rtb.Render($script:Window)
            $enc = New-Object System.Windows.Media.Imaging.PngBitmapEncoder
            $enc.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($rtb))
            $fs = [System.IO.File]::Create($DevSnapshot)
            $enc.Save($fs)
            $fs.Close()
        }
        catch { [System.IO.File]::WriteAllText($DevSnapshot + '.error.txt', ($_ | Out-String)) }
        if ($DevExitAfterSnapshot) { Invoke-Exit }
    })
    $devTimer.Start()
}

try {
    [System.Windows.Threading.Dispatcher]::Run()
}
finally {
    try { $script:TrayIcon.Visible = $false; $script:TrayIcon.Dispose() } catch { }
    Stop-Engine
    if ($script:SingleInstance) {
        try { $script:SingleInstance.ReleaseMutex() } catch { }
        try { $script:SingleInstance.Dispose() } catch { }
    }
}

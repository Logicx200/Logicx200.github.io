# reaction-cam.ps1 -- watch the live pet and capture one screenshot per state change.
#
# Verification aid for task-7 (section A of the acceptance): every 500 ms it reads the
# engine's state.json + signals.json, and whenever the activity category changes it
# captures the pet window (a short burst for the one-shot faces, which live 1.6-3 s)
# and appends one line naming the log field that triggered the change:
#
#   time | state | label | color | pose | detail | reason | tool=... | turn=... | idle
#
# Pure ASCII on purpose: PS 5.1 reads a BOM-less .ps1 as ANSI (see
# pet/REACTIONS-SPEC.md section 10).
param(
  [int]$Seconds = 1200,
  [int]$IntervalMs = 500,
  [string]$OutDir = (Join-Path $PSScriptRoot 'react'),
  [string]$Log = (Join-Path $PSScriptRoot 'task7-reactions.log'),
  [string]$RendererDir = (Join-Path (Split-Path $PSScriptRoot -Parent) 'renderer'),
  [int]$Keep = 160
)

Add-Type -AssemblyName System.Drawing
Add-Type -Namespace RC -Name Win -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
public delegate bool EnumProc(IntPtr h, IntPtr p);
'@

$stateFile = Join-Path $RendererDir 'state.json'
$signalsFile = Join-Path $RendererDir 'signals.json'
$short = @('error', 'celebrating', 'listening')

if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

function Read-Json([string]$path) {
  if (-not (Test-Path -LiteralPath $path)) { return $null }
  try { return ([System.IO.File]::ReadAllText($path, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json) } catch { return $null }
}

function Get-PetRect {
  $script:found = [IntPtr]::Zero
  $cb = [RC.Win+EnumProc] {
    param($h, $p)
    $sb = New-Object System.Text.StringBuilder 128
    [void][RC.Win]::GetWindowText($h, $sb, 128)
    if ($sb.ToString() -eq 'DSH pet' -and [RC.Win]::IsWindowVisible($h)) { $script:found = $h }
    return $true
  }
  [void][RC.Win]::EnumWindows($cb, [IntPtr]::Zero)
  if ($script:found -eq [IntPtr]::Zero) { return $null }
  $r = New-Object RC.Win+RECT
  if (-not [RC.Win]::GetWindowRect($script:found, [ref]$r)) { return $null }
  return @{ X = $r.Left; Y = $r.Top; W = ($r.Right - $r.Left); H = ($r.Bottom - $r.Top) }
}

function Save-Shot([string]$path, $rect) {
  try {
    $bmp = New-Object System.Drawing.Bitmap $rect.W, $rect.H
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($rect.X, $rect.Y, 0, 0, (New-Object System.Drawing.Size($rect.W, $rect.H)))
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    return $true
  } catch { return $false }
}

$deadline = (Get-Date).AddSeconds($Seconds)
$last = ''
$lastToolAt = 0
$seq = 0
$lines = New-Object System.Collections.ArrayList
while ((Get-Date) -lt $deadline) {
  $state = Read-Json $stateFile
  $sig = Read-Json $signalsFile
  # A new tool signal is worth a shot on its own: the reaction layer reacts to it
  # (glasses, device, pen) even when the activity category happens not to change.
  $toolAt = if ($null -ne $sig -and $null -ne $sig.tool) { [double]$sig.tool.at } else { 0 }
  $toolNew = $toolAt -gt 0 -and $toolAt -ne $lastToolAt
  if ($null -ne $state) {
    $key = [string]$state.state
    if ($key -ne $last -or $toolNew) {
      $changedState = $key -ne $last
      $last = $key
      $lastToolAt = $toolAt
      $seq += 1
      $tool = if ($null -ne $sig) { $sig.tool } else { $null }
      $turn = if ($null -ne $sig) { $sig.turn } else { $null }
      $stamp = Get-Date -Format 'HH:mm:ss.fff'
      $toolText = if ($null -ne $tool) { '{0}/{1}/ok={2}/err={3}' -f $tool.name, $tool.phase, $tool.ok, $tool.error } else { '-' }
      $turnText = if ($null -ne $turn) { '{0}/ms={1}/tok={2}' -f $turn.reason, $turn.ms, $turn.tokens } else { '-' }
      $line = '{0} | {1} | {2} | {3} | {4} | {5} | {6} | tool={7} | turn={8} | idleMs={9} | trigger={10}' -f `
        $stamp, $state.state, $state.label, $state.color, $state.pose, $state.detail, $state.reason, `
        $toolText, $turnText, $(if ($null -ne $sig) { $sig.idleMs } else { '-' }), $(if ($changedState) { 'state' } else { 'tool-signal' })
      [void]$lines.Add($line)
      $rect = Get-PetRect
      if ($null -ne $rect -and $rect.W -gt 0) {
        # The page polls state.json/signals.json every 1.5 s and only then pulls the
        # face, so shooting immediately catches the *previous* expression. Wait for
        # two polls on the calm states (their category persists) and one plus a short
        # burst on the one-shot reactions, whose TTL is only 1.6-3.2 s.
        $shortShot = ($short -contains $key) -or ($null -ne $tool -and $tool.phase -eq 'result' -and $tool.ok -eq $false)
        if ($shortShot) {
          Start-Sleep -Milliseconds 1600
          $count = 4
          $gapMs = 600
        } else {
          Start-Sleep -Milliseconds 2400
          $count = 1
          $gapMs = 0
        }
        for ($i = 0; $i -lt $count; $i++) {
          if ($i -gt 0) { Start-Sleep -Milliseconds $gapMs }
          $name = 'react-{0:d3}-{1}-{2}.png' -f $seq, $key, $i
          [void](Save-Shot (Join-Path $OutDir $name) $rect)
        }
      }
    }
  }
  Start-Sleep -Milliseconds $IntervalMs
}
# newest lines first, newest files kept
$all = @(Get-Content -LiteralPath $Log -ErrorAction SilentlyContinue) + $lines.ToArray()
$all | Set-Content -LiteralPath $Log -Encoding UTF8
$files = @(Get-ChildItem -LiteralPath $OutDir -Filter 'react-*.png' | Sort-Object LastWriteTime -Descending)
if ($files.Count -gt $Keep) { $files | Select-Object -Skip $Keep | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force } }
Write-Host ('reaction-cam: {0} state change(s), {1} shot(s) kept in {2}' -f $seq, (Get-ChildItem -LiteralPath $OutDir -Filter 'react-*.png').Count, $OutDir)

# reactions-visibility.ps1 -- task-14 forensics: capture the PRODUCTION pet window as
# pixels, frame by frame, so the reaction layer can be judged by "can a human see it"
# instead of by mechanism readings.  Pure ASCII (PS 5.1 reads a BOM-less .ps1 as ANSI).
#
# Modes
#   watch   : capture a frame every -IntervalMs and log the state/signals snapshot that
#             was on disk at that moment.  Run it in the BACKGROUND while you work: every
#             tool call of the DSH session is a real production trigger, so the frames end
#             up labelled by the trigger that produced them.
#   forced  : drive force-state.json through a plan (SUPPLEMENTARY evidence only - it
#             proves the page can render a state, not that production renders it).
#
# The window is never touched (no SetWindowPos, no topmost games): frames come from
# CopyFromScreen of the character's own box, exactly as the user sees it.
param(
  # path-independent defaults: this script lives in pet\host\experiments, so no
  # non-ASCII literal is needed (PS 5.1 reads a BOM-less .ps1 as ANSI and a Chinese
  # path here would arrive mangled - that bug cost one capture run already)
  [string]$Here = (Split-Path -Parent $PSScriptRoot),
  [string]$OutDir = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'showcase\reactions-test'),
  [ValidateSet('watch', 'forced')][string]$Mode = 'watch',
  [int]$Seconds = 120,
  [int]$IntervalMs = 600,
  [string]$Tag = 'prod',
  [string]$Note = ''
)
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Drawing

$frameDir = Join-Path $OutDir 'frames'
New-Item -ItemType Directory -Path $frameDir -Force | Out-Null
$modelPath = Join-Path $Here 'model.json'
$statePath = Join-Path $Here '..\renderer\state.json'
$signalsPath = Join-Path $Here '..\renderer\signals.json'
$forcePath = Join-Path $Here 'force-state.json'

function Read-JsonFile([string]$p) {
  try {
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    return [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $p), [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
  } catch { return $null }
}
function Snapshot {
  $st = Read-JsonFile $statePath
  $sg = Read-JsonFile $signalsPath
  $toolName = $null; $toolPhase = $null; $errName = $null; $turnPhase = $null
  if ($sg) {
    if ($sg.tool) { $toolName = $sg.tool.name; $toolPhase = $sg.tool.phase }
    if ($sg.lastError) { $errName = ([string]$sg.lastError.name + '/' + [string]$sg.lastError.error) }
    if ($sg.turn) { $turnPhase = $sg.turn.phase }
  }
  return [pscustomobject]@{
    state = $(if ($st) { $st.state } else { $null })
    label = $(if ($st) { $st.label } else { $null })
    color = $(if ($st) { $st.color } else { $null })
    pose = $(if ($st) { $st.pose } else { $null })
    detail = $(if ($st) { $st.detail } else { $null })
    stateAt = (Get-Item -LiteralPath $statePath -ErrorAction SilentlyContinue).LastWriteTime.ToString('HH:mm:ss.fff')
    signalsAt = (Get-Item -LiteralPath $signalsPath -ErrorAction SilentlyContinue).LastWriteTime.ToString('HH:mm:ss.fff')
    tool = $toolName; toolPhase = $toolPhase; lastError = $errName; turn = $turnPhase
    stateBytes = (Get-Item -LiteralPath $statePath -ErrorAction SilentlyContinue).Length
    signalBytes = (Get-Item -LiteralPath $signalsPath -ErrorAction SilentlyContinue).Length
  }
}

# the crop: the character's box (page.model uses x/y, screen.model uses left/top)
$j = Read-JsonFile $modelPath
if (-not $j) { Write-Host 'FAIL: model.json missing - is the pet running?'; exit 1 }
$m = $j.screen.model
$pad = 6
$cropX = [int]$m.left - $pad
$cropY = [int]$m.top - $pad
$cropW = [int]($m.right - $m.left) + 2 * $pad
$cropH = [int]($m.bottom - $m.top) + 2 * $pad
Write-Host ("crop = {0},{1} {2}x{3}  (character {4},{5}..{6},{7})" -f $cropX, $cropY, $cropW, $cropH, $m.left, $m.top, $m.right, $m.bottom)

$index = New-Object System.Collections.ArrayList
$seq = 0
function Capture([string]$label, [string]$mode, [string]$trigger, [string]$note) {
  $script:seq = $script:seq + 1
  $snap = Snapshot
  $bmp = New-Object System.Drawing.Bitmap $cropW, $cropH
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($cropX, $cropY, 0, 0, (New-Object System.Drawing.Size($cropW, $cropH)))
  $g.Dispose()
  $file = ('{0}-{1:d4}-{2}.png' -f $mode, $script:seq, $label)
  $bmp.Save((Join-Path $frameDir $file), [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  [void]$index.Add([pscustomobject]@{
    i = $script:seq; file = $file; label = $label; mode = $mode; trigger = $trigger; note = $note
    at = (Get-Date).ToString('HH:mm:ss.fff')
    state = $snap.state; stateLabel = $snap.label; color = $snap.color; pose = $snap.pose; detail = $snap.detail
    tool = $snap.tool; toolPhase = $snap.toolPhase; lastError = $snap.lastError; turn = $snap.turn
    stateAt = $snap.stateAt; signalsAt = $snap.signalsAt
    stateBytes = $snap.stateBytes; signalBytes = $snap.signalBytes
    crop = ('{0},{1},{2},{3}' -f $cropX, $cropY, $cropW, $cropH)
  })
  Write-Host ('{0,3} {1,-28} state={2,-11} pose={3,-9} tool={4}/{5} err={6}' -f $script:seq, $label, $snap.state, $snap.pose, $snap.tool, $snap.toolPhase, $snap.lastError)
}

if ($Mode -eq 'watch') {
  Write-Host ("watch mode: {0} s at {1} ms -> {2}" -f $Seconds, $IntervalMs, $Tag)
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    Capture -label ('w' + $script:seq) -mode $Tag -trigger 'production' -note $Note
    Start-Sleep -Milliseconds $IntervalMs
  }
} else {
  # forced plan: state + pose + optional act / props.  Each entry gets 2.6 s to land
  # (the page polls nothing here - the host pushes the payload on every tick).
  # The pose names MUST be the real POSE_VALUES (pet\state.mjs): a wrong name silently
  # falls back and the tile then shows "no change" for a reason that has nothing to do
  # with visibility.  These payloads mirror pet\showcase\states.json exactly.
  $plan = @(
    @{ label = 'f-idle'; payload = @{ state = 'idle'; pose = 'idle'; clearBubble = $true } },
    @{ label = 'f-reading'; payload = @{ state = 'reading'; pose = 'reading'; clearBubble = $true } },
    @{ label = 'f-writing'; payload = @{ state = 'writing'; pose = 'scribble'; clearBubble = $true } },
    @{ label = 'f-running'; payload = @{ state = 'running'; pose = 'sleeves'; clearBubble = $true } },
    @{ label = 'f-thinking'; payload = @{ state = 'thinking'; pose = 'thinking'; clearBubble = $true } },
    @{ label = 'f-error'; payload = @{ state = 'error'; pose = 'gloomy'; clearBubble = $true } },
    @{ label = 'f-celebrating'; payload = @{ state = 'celebrating'; pose = 'happy'; clearBubble = $true } },
    @{ label = 'f-listening'; payload = @{ state = 'listening'; pose = 'starry'; clearBubble = $true } },
    @{ label = 'f-team'; payload = @{ state = 'team'; pose = 'team'; clearBubble = $true } },
    @{ label = 'f-stale'; payload = @{ state = 'stale'; pose = 'sleepy'; clearBubble = $true } },
    @{ label = 'f-offline'; payload = @{ state = 'offline'; pose = 'offline'; clearBubble = $true } },
    @{ label = 'f-decor-glasses'; payload = @{ state = 'idle'; pose = 'idle'; props = @('glassesRound'); clearBubble = $true } },
    @{ label = 'f-decor-phone'; payload = @{ state = 'idle'; pose = 'idle'; props = @('phone'); clearBubble = $true } },
    @{ label = 'f-act-love'; payload = @{ state = 'idle'; pose = 'idle'; act = 'love'; clearBubble = $true } },
    @{ label = 'f-act-selfie'; payload = @{ state = 'idle'; pose = 'idle'; act = 'selfie'; clearBubble = $true } }
  )
  foreach ($item in $plan) {
    $json = $item.payload | ConvertTo-Json -Compress -Depth 4
    [System.IO.File]::WriteAllText($forcePath, $json, (New-Object System.Text.UTF8Encoding($false)))
    Start-Sleep -Milliseconds 2600
    Capture -label $item.label -mode $Tag -trigger ('force-state.json: ' + $json) -note 'supplementary (dev channel)'
  }
  # release: deleting the file makes the host push null -> the page returns to production
  Remove-Item -LiteralPath $forcePath -Force -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 2600
  Capture -label 'f-released' -mode $Tag -trigger 'force-state.json deleted' -note 'back to production'
}

$idxPath = Join-Path $OutDir ($Tag + '-index.json')
$index | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $idxPath -Encoding UTF8
Write-Host ('frames: ' + $index.Count + ' -> ' + $frameDir)
Write-Host ('index : ' + $idxPath)

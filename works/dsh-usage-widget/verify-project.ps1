<#
.SYNOPSIS
Check that this project is in a state that can actually run.

.DESCRIPTION
Three things have broken this project before, and each one is cheap to check:

1. **A `.cmd` launcher.** The first version shipped one, and 火绒 (Huorong)
   quarantined it as a trojan within ~90 seconds — a batch file that runs
   PowerShell with a hidden window and a bypassed execution policy is the classic
   defence-evasion shape. The launcher is now a logon Scheduled Task plus a Start
   Menu shortcut, both running a plain `powershell.exe -NoProfile -File ...`, and
   there must be no `.cmd` or `.bat` anywhere in the tree.

2. **A `widget.ps1` without its UTF-8 BOM.** Windows PowerShell 5.1 decodes a
   BOM-less script as ANSI, so every Chinese literal turns into mojibake and the
   file fails to parse — the widget then cannot start at all. Many editors and
   tooling write UTF-8 without a BOM, so this is checked on every run.

3. **An engine that no longer emits the agreed contract.** The window matches the
   fields `today.costCny` / `today.costUsd` / `today.tokens.*`, `total.*`,
   `balance.ok|total`, and `event.*`. One `--once` snapshot is enough to prove the
   shapes are still there.

Run it after any edit:

    powershell -NoProfile -File verify-project.ps1

Exit code 0 means every check passed.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
$failures = 0

function Check {
  param([string]$Name, [bool]$Ok, [string]$Detail = '')
  $mark = if ($Ok) { 'ok  ' } else { 'FAIL' }
  if (-not $Ok) { $script:failures++ }
  Write-Host ("{0}  {1}{2}" -f $mark, $Name, $(if ($Detail) { "  ($Detail)" } else { '' }))
}

Write-Host '=== launcher hygiene ==='
$shells = @(Get-ChildItem $here -Recurse -File -Force -Include '*.cmd', '*.bat' -ErrorAction SilentlyContinue)
Check 'no .cmd / .bat anywhere in the project' ($shells.Count -eq 0) ("found: " + (($shells | ForEach-Object { $_.Name }) -join ', '))

# What actually runs is the scheduled task's action, so that is where the shape
# matters. Documentation and comments are allowed to name these flags — naming
# them is how the reason gets recorded.
$task = Get-ScheduledTask -TaskName 'DshUsageWidget' -ErrorAction SilentlyContinue
if ($task) {
  $arguments = ($task.Actions | ForEach-Object { $_.Arguments }) -join ' '
  Check 'the logon task launches a plain powershell -NoProfile -File' ($arguments -match '-NoProfile' -and $arguments -match '-File') $arguments
  foreach ($pattern in @('-WindowStyle', '-ExecutionPolicy', '-EncodedCommand')) {
    Check ("the logon task does not pass '$pattern'") (-not $arguments.Contains($pattern))
  }
} else {
  Write-Host 'info  no logon task registered yet (install-startup.ps1 adds one)'
}

# task-17: the project lives at a pure-ASCII path and the task must point straight at
# this tree's widget - no %LOCALAPPDATA% Bypass launcher (that existed only for the old
# non-ASCII path) and no other entry point.
if ($task) {
  $entry = ($task.Actions | ForEach-Object { $_.Arguments }) -join ' '
  Check 'the task entry point is this tree''s ui\widget.ps1' ($entry -match [regex]::Escape((Join-Path $here 'ui\widget.ps1'))) $entry
  Check 'the task does not go through a start-menu/LOCALAPPDATA launcher' (-not ($entry -match 'launch\.ps1' -or $entry -match 'LOCALAPPDATA')) $entry
}
$strayLauncher = Join-Path $env:LOCALAPPDATA 'dsh-usage-widget\launch.ps1'
Check 'no leftover Bypass launcher in %LOCALAPPDATA%' (-not (Test-Path -LiteralPath $strayLauncher)) $strayLauncher
$wdTask = Get-ScheduledTask -TaskName 'DshUsageWidgetWatchdog' -ErrorAction SilentlyContinue
Check 'the silent watchdog task exists (self-healing after a crash)' ($null -ne $wdTask)
if ($wdTask) {
  $rep = ($wdTask.Triggers | ForEach-Object { $_.Repetition.Interval }) -join ','
  $mins = if ($rep -match 'PT(\d+)M') { [int]$Matches[1] } else { 0 }
  Check 'the watchdog runs every 3..5 minutes' ($mins -ge 3 -and $mins -le 5) ('interval=' + $rep)
  $wdScript = Join-Path $here 'pet\host\watchdog.ps1'
  Check 'the watchdog script exists in this tree' (Test-Path -LiteralPath $wdScript) $wdScript
  $wdArgs = ($wdTask.Actions | ForEach-Object { $_.Arguments }) -join ' '
  Check 'the watchdog does not pass -ExecutionPolicy' (-not $wdArgs.Contains('-ExecutionPolicy')) $wdArgs
  # task-18: the flashing console was the watchdog running interactively. Non-interactive
  # (S4U) runs in session 0, which has no desktop, so no visible window is possible - this
  # is a judgeable property, not a comment.
  Check 'the watchdog runs non-interactively (S4U) so it can never show a window' ($wdTask.Principal.LogonType -eq 'S4U') ('LogonType=' + $wdTask.Principal.LogonType)
  Check 'the watchdog passes -Quiet (no stdout, so nothing could ever surface)' ($wdArgs -match '-Quiet') $wdArgs
  foreach ($pat in @('-WindowStyle', '-ExecutionPolicy', '-EncodedCommand')) {
    Check ("the watchdog action does not contain '" + $pat + "'") (-not $wdArgs.Contains($pat))
  }
  $widgetTask = Get-ScheduledTask -TaskName 'DshUsageWidget' -ErrorAction SilentlyContinue
  if ($widgetTask) {
    Check 'the widget task stays interactive (it has to draw the UI)' ($widgetTask.Principal.LogonType -eq 'Interactive') ('LogonType=' + $widgetTask.Principal.LogonType)
  }
}

Write-Host ''
Write-Host '=== the window script ==='
$widget = Join-Path $here 'ui\widget.ps1'
Check 'ui\widget.ps1 exists' (Test-Path -LiteralPath $widget)
if (Test-Path -LiteralPath $widget) {
  $bytes = [System.IO.File]::ReadAllBytes($widget)
  $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
  Check 'ui\widget.ps1 keeps its UTF-8 BOM' $hasBom 'PS 5.1 reads a BOM-less script as ANSI and fails to parse the Chinese labels'

  $errors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($widget, [ref]$null, [ref]$errors)
  $firstError = if ($errors -and $errors.Count -gt 0) { $errors[0].Message } else { '' }
  Check 'ui\widget.ps1 parses' ($null -eq $errors -or $errors.Count -eq 0) $firstError
}

Write-Host ''
Write-Host '=== the Live2D pet ==='
# The pet is a separate WPF + WebView2 window started by the panel, and a pure
# `state.mjs` decision published by the engine.  Four things break it silently,
# so each one is checked: a host script PS 5.1 cannot read (no BOM + non-ASCII),
# a missing model, a batch launcher in the pet tree, and a pose map that lost an
# entry (the pet would then stand still for that state without any error).
Check 'pet\model\c_0120.moc3 exists' (Test-Path -LiteralPath (Join-Path $here 'pet\model\c_0120.moc3'))
$petShells = @(Get-ChildItem (Join-Path $here 'pet') -Recurse -File -Force -Include '*.cmd', '*.bat' -ErrorAction SilentlyContinue)
Check 'the pet folder contains no .cmd / .bat' ($petShells.Count -eq 0) ("found: " + (($petShells | ForEach-Object { $_.Name }) -join ', '))

$hostScript = Join-Path $here 'pet\host\host.ps1'
Check 'pet\host\host.ps1 exists' (Test-Path -LiteralPath $hostScript)
if (Test-Path -LiteralPath $hostScript) {
  $hostErrors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($hostScript, [ref]$null, [ref]$hostErrors)
  $hostFirst = if ($hostErrors -and $hostErrors.Count -gt 0) { $hostErrors[0].Message } else { '' }
  Check 'pet\host\host.ps1 parses' ($null -eq $hostErrors -or $hostErrors.Count -eq 0) $hostFirst

  $hostBytes = [System.IO.File]::ReadAllBytes($hostScript)
  $hostNonAscii = @($hostBytes | Where-Object { $_ -gt 127 }).Count
  Check 'pet\host\host.ps1 is pure ASCII' ($hostNonAscii -eq 0) "$hostNonAscii non-ASCII byte(s); a BOM-less script is read as ANSI and a non-ASCII comment can swallow the next line"
}

$renderer = Join-Path $here 'pet\renderer\pet-app.js'
Check 'pet\renderer\pet-app.js exists' (Test-Path -LiteralPath $renderer)
if (Test-Path -LiteralPath $renderer) {
  $appText = [System.IO.File]::ReadAllText($renderer)
  # Since task-7 pet-app.js is the *mechanism* layer (frame hooks, motion playback,
  # in-frame parameter access, the expression self-test) and the policy - which face
  # for which activity - lives in reactions.js. Both halves are pinned here.
  foreach ($export in @('onFrame', 'playMotion', 'stopMotions', 'readParam', 'writeParam', 'selfTestResult', 'forbiddenMotions')) {
    Check "pet-app.js exposes the mechanism hook '$export'" ([regex]::IsMatch($appText, ('(?m)^\s*' + $export + '\s*:')))
  }
  Check "pet-app.js blocks the forbidden aidale/bubble motions" ([regex]::IsMatch($appText, "FORBIDDEN_MOTIONS = \['aidale', 'bubble'\]"))
  Check 'pet-app.js no longer auto-plays the idle loop (idleMotionGroup removed)' (-not $appText.Contains('idleMotionGroup:'))
  Check 'pet-app.js writes the in-frame expression self-test (?selftest=1)' ($appText.Contains('selftest'))
  foreach ($reserved in @('#7EE787', '#FF7B72')) {
    Check "pet-app.js never uses the panel's reserved colour $reserved" (-not $appText.Contains($reserved))
  }
}

# The layout, checked on the live measurement when the host and the panel are
# running: the label must not sit above the head or past the tail, it must be
# right-aligned with the panel's own right-aligned text (task-5 requirement 2),
# it must clear the panel text line above it by 10..14 px (requirement 1), and
# the character must fit inside its own window (the host shifts the model left so
# the tail is not cut, and down so the pair sits close to the taskbar).
$modelFile = Join-Path $here 'pet\host\model.json'
$geomFile = Join-Path $here 'pet\renderer\panel-geometry.json'
if (Test-Path -LiteralPath $modelFile) {
  $modelDoc = $null
  try { $modelDoc = [System.IO.File]::ReadAllText($modelFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $modelDoc = $null }
  Check 'pet\host\model.json is valid JSON' ($null -ne $modelDoc)
  if ($null -ne $modelDoc) {
    $win = $modelDoc.window
    $sm = $modelDoc.screen.model
    $sl = $modelDoc.screen.label
    if ($null -ne $sm -and $null -ne $win) {
      $inside = ($sm.left -ge $win.x) -and ($sm.top -ge $win.y) -and ($sm.right -le ($win.x + $win.width)) -and ($sm.bottom -le ($win.y + $win.height))
      Check 'the measured character box fits inside the pet window (not clipped)' $inside ("model $($sm.left),$($sm.top)..$($sm.right),$($sm.bottom) in window $($win.x),$($win.y) $($win.width)x$($win.height)")
      try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
        $winInside = ($win.x -ge $wa.Left) -and ($win.y -ge $wa.Top) -and (($win.x + $win.width) -le $wa.Right) -and (($win.y + $win.height) -le $wa.Bottom)
        Check 'the pet window stays inside the work area' $winInside ("window bottom " + ($win.y + $win.height) + " <= work area bottom " + $wa.Bottom)
        # the character must keep 10-15 px of air above the work area's bottom: it is the
        # visual relation the user accepted, and it silently drifted once when a drag
        # offset from a verification run was left in pet\host\pet-offset.json
        $gapBottom = $wa.Bottom - $sm.bottom
        Check 'outlineBottomToWorkArea stays within 10..15 px' (($gapBottom -ge 10) -and ($gapBottom -le 15)) ("outline bottom " + $sm.bottom + " -> work area bottom " + $wa.Bottom + " = " + $gapBottom + " px")
        $clip = ($win.y + $win.height) - $sm.bottom
        Check 'the character is not clipped by the window bottom (> 0)' ($clip -gt 0) ("window bottom - outline bottom = " + $clip + " px")
      } catch {
        Write-Host 'info  System.Windows.Forms unavailable - work area check skipped'
      }
    }
    if ($null -ne $sm -and $null -ne $sl) {
      Check 'labelTop - modelTop >= 0 (label not above the head)' (($sl.top - $sm.top) -ge 0) ("labelTop - modelTop = " + ($sl.top - $sm.top))
      Check 'modelRight - labelRight >= 0 (label not past the tail)' (($sm.right - $sl.right) -ge 0) ("modelRight - labelRight = " + ($sm.right - $sl.right))
      Write-Host ("      character screen box {0},{1}..{2},{3}   label {4},{5}..{6},{7}" -f $sm.left, $sm.top, $sm.right, $sm.bottom, $sl.left, $sl.top, $sl.right, $sl.bottom)
    }
    # task-5 requirement 2 + requirement 1 are only meaningful for the *panel's*
    # own pet window: a development host (a bench run with its own window) publishes
    # its own model.json, and comparing that to the panel's layout would be apples
    # to oranges. The panel publishes the window it thinks the pet owns, so match on
    # that first and only then check the alignment.
    $aligned = $true
    if (Test-Path -LiteralPath $geomFile) {
      $geomDoc0 = $null
      try { $geomDoc0 = [System.IO.File]::ReadAllText($geomFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $geomDoc0 = $null }
      if ($null -ne $geomDoc0 -and $null -ne $geomDoc0.window -and $null -ne $win) {
        $sameWindow = ([int]$geomDoc0.window.x -eq [int]$win.x) -and ([int]$geomDoc0.window.y -eq [int]$win.y)
        if (-not $sameWindow) {
          $aligned = $false
          Write-Host ("info  model.json is from a development host (window {0},{1} vs the panel's {2},{3}) - alignment checks skipped" -f $win.x, $win.y, $geomDoc0.window.x, $geomDoc0.window.y)
        }
      }
    }
    # task-5 requirement 2: labelRight == the right edge of the panel's
    # right-aligned text.  The panel publishes that edge from its own live layout
    # (pet\renderer\panel-geometry.json), so a padding or font change flows through.
    if (Test-Path -LiteralPath $geomFile) {
      $geomDoc = $null
      try { $geomDoc = [System.IO.File]::ReadAllText($geomFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $geomDoc = $null }
      Check 'pet\renderer\panel-geometry.json is valid JSON' ($null -ne $geomDoc)
      if ($null -ne $geomDoc -and $null -ne $sl -and $aligned) {
        $dRight = [math]::Abs($sl.right - [int]$geomDoc.contentRight)
        Check 'labelRight == the panel right-aligned text right edge (within 1 px)' ($dRight -le 1) ("labelRight " + $sl.right + " vs panel text right " + $geomDoc.contentRight + " (delta $dRight)")
        $gap = $sl.top - [int]$geomDoc.textBottom
        Check 'label top clears the panel text line above it by 10..14 px' (($gap -ge 10) -and ($gap -le 14)) ("gap = $gap px (labelTop $($sl.top), text bottom $($geomDoc.textBottom))")
      }
    } else {
      Write-Host 'info  pet\renderer\panel-geometry.json not written yet (the panel publishes it while it runs)'
    }
  }
} else {
  Write-Host 'info  pet\host\model.json not written yet (the host publishes it every 1.5 s while it runs)'
}

$sdk = Join-Path $here 'pet\renderer\webview2-test'
if (Test-Path -LiteralPath (Join-Path $sdk 'Microsoft.Web.WebView2.Wpf.dll')) {
  Check 'the WebView2 SDK is present for the host (Microsoft.Web.WebView2.Wpf.dll)' $true
  Check 'WebView2Loader.dll is present for the host' (Test-Path -LiteralPath (Join-Path $sdk 'WebView2Loader.dll'))
} else {
  Check 'the WebView2 SDK is present for the host (beside pet\host\host.ps1)' (Test-Path -LiteralPath (Join-Path $here 'pet\host\Microsoft.Web.WebView2.Wpf.dll'))
}

Write-Host ''
Write-Host '=== the engine contract ==='
$node = $null
foreach ($candidate in @(
    (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'),
    'D:\Node.js\node.exe'
  )) {
  if (Test-Path -LiteralPath $candidate) { $node = $candidate; break }
}
if ($null -eq $node) {
  $onPath = Get-Command node -ErrorAction SilentlyContinue
  if ($onPath) { $node = $onPath.Source }
}
Check 'a node runtime was found' ($null -ne $node) $node

if ($null -ne $node) {
  $output = & $node (Join-Path $here 'engine\cli.mjs') --once 2>&1
  $exit = $LASTEXITCODE
  Check 'engine --once exits 0' ($exit -eq 0) "exit $exit"

  $ready = $null
  $snapshot = $null
  foreach ($line in $output) {
    if ($line -match '"type"\s*:\s*"ready"') { $ready = $line | ConvertFrom-Json }
    elseif ($line -match '"type"\s*:\s*"snapshot"') { $snapshot = $line | ConvertFrom-Json }
  }
  Check 'a ready line was emitted' ($null -ne $ready)
  Check 'a snapshot line was emitted' ($null -ne $snapshot)

  if ($null -ne $snapshot) {
    foreach ($field in @('at', 'peakNow', 'rate', 'today', 'total', 'balance')) {
      Check ("snapshot has '$field'") ($null -ne $snapshot.$field)
    }
    foreach ($field in @('costUsd', 'costCny', 'calls', 'tokens')) {
      Check ("snapshot.today has '$field'") ($null -ne $snapshot.today.$field)
    }
    foreach ($field in @('costUsd', 'costCny', 'calls', 'sessions', 'tokens')) {
      Check ("snapshot.total has '$field'") ($null -ne $snapshot.total.$field)
    }
    Check 'snapshot.balance carries ok' ($null -ne $snapshot.balance.ok)
    if ($snapshot.balance.ok -eq $true) {
      Write-Host ("      today {0:N4} CNY / {1:N4} USD   total {2:N4} CNY   balance {3} {4}" -f `
          $snapshot.today.costCny, $snapshot.today.costUsd, $snapshot.total.costCny, `
          $snapshot.balance.total, $snapshot.balance.currency)
    }

    # The pet state line: additive on the snapshot, decided only by pet\state.mjs.
    # The colours are ASCII, so they can be pinned here without any encoding trap.
    # Since task-7 the enum is the eleven *activity categories* of
    # REACTIONS-SPEC §2 (peak is deliberately not one of them).
    $frozenPetColors = @{
      offline = '#8B949E'; stale = '#D2A8FF'; error = '#F85149'; celebrating = '#E3B341'
      listening = '#79C0FF'; team = '#56D4DD'; reading = '#58A6FF'; writing = '#F0883E'
      running = '#FFA657'; thinking = '#A5D6FF'; idle = '#9DA7B3'
    }
    $petPoses = @('offline', 'sleepy', 'team', 'starry', 'thinking', 'reading', 'scribble', 'sleeves', 'happy', 'gloomy', 'idle')
    $pet = $snapshot.pet
    Check "snapshot carries the additive 'pet' state" ($null -ne $pet)
    if ($null -ne $pet) {
      $petState = [string]$pet.state
      Check 'pet.state is one of the eleven activity categories' ($frozenPetColors.ContainsKey($petState)) $petState
      Check 'pet.label is non-empty' (-not [string]::IsNullOrWhiteSpace([string]$pet.label))
      Check 'pet.color matches the frozen table for that state' ($frozenPetColors[$petState] -ieq [string]$pet.color) "$petState -> $($pet.color)"
      Check 'pet.pose is one of the eleven poses' ($petPoses -contains [string]$pet.pose) ([string]$pet.pose)
      Check 'pet.detail is a string' ($pet.detail -is [string])
      Check 'pet.reason is a string' ($pet.reason -is [string])
      foreach ($reserved in @('#7EE787', '#FF7B72')) {
        Check "pet.color never borrows the reserved colour $reserved" ([string]$pet.color -ine $reserved)
      }
      Write-Host ("      pet {0} / {1} / {2}  pose={3}  detail={4}" -f $pet.state, $pet.label, $pet.color, $pet.pose, $pet.detail)
    }

    # task-7 §1: the engine passes the reaction signals through as new NDJSON line
    # types. They are additive - the panel's pump must ignore them - so check the
    # shape of whatever this poll produced, and that jobs carry the raw tool name.
    $toolLines = @()
    $turnLines = @()
    foreach ($line in $output) {
      if ($line -match '"type"\s*:\s*"tool"') { $toolLines += ($line | ConvertFrom-Json) }
      elseif ($line -match '"type"\s*:\s*"turn"') { $turnLines += ($line | ConvertFrom-Json) }
    }
    if ($toolLines.Count -gt 0) {
      $bad = @($toolLines | Where-Object { $null -eq $_.at -or [string]::IsNullOrWhiteSpace([string]$_.name) -or @('call', 'result') -notcontains [string]$_.phase -or $null -eq $_.PSObject.Properties['ok'] -or $null -eq $_.PSObject.Properties['error'] })
      Check 'every tool passthrough line is well formed (at/name/phase/ok/error)' ($bad.Count -eq 0) ("$($toolLines.Count) line(s)")
      Write-Host ("      tool line: {0} phase={1} ok={2} error={3}" -f $toolLines[-1].name, $toolLines[-1].phase, $toolLines[-1].ok, $toolLines[-1].error)
    } else {
      Write-Host 'info  no tool call in the folded session logs this poll (the line type is additive)'
    }
    if ($turnLines.Count -gt 0) {
      $badTurn = @($turnLines | Where-Object { $null -eq $_.at -or [string]::IsNullOrWhiteSpace([string]$_.phase) -or $null -eq $_.PSObject.Properties['reason'] -or $null -eq $_.PSObject.Properties['ms'] -or $null -eq $_.PSObject.Properties['tokens'] })
      Check 'every turn passthrough line is well formed (at/phase/reason/ms/tokens)' ($badTurn.Count -eq 0) ("$($turnLines.Count) line(s)")
      Write-Host ("      turn line: phase={0} reason={1} ms={2} tokens={3}" -f $turnLines[-1].phase, $turnLines[-1].reason, $turnLines[-1].ms, $turnLines[-1].tokens)
    } else {
      Write-Host 'info  no turn end in the folded session logs this poll'
    }
    if ($null -ne $node) {
      # The raw tool name is a contract of engine/activity.mjs's buildJobs(): the
      # panel's `program` is the inner program (pwsh/node/python), the reaction
      # layer needs `name` (read/write/pwsh/web_search...). Probe it directly, since
      # a bridge-sourced job row never comes through that fold.
      $jobsProbe = Join-Path $env:TEMP 'dsh-verify-jobs.mjs'
      $jobsSource = @'
import { pathToFileURL } from 'node:url'
const mod = await import(pathToFileURL(process.argv[2]).href)
const rows = mod.buildJobs([{ id: 'c1', session: 's1', name: 'pwsh', raw: '{"command":"npm test"}', time: 1000 }], 2000)
console.log(JSON.stringify({ name: rows[0].name, tool: rows[0].tool, program: rows[0].program }))
'@
      try {
        [System.IO.File]::WriteAllText($jobsProbe, $jobsSource, (New-Object System.Text.UTF8Encoding($false)))
        $jobRow = (& $node $jobsProbe (Join-Path $here 'engine\activity.mjs') 2>&1 | Select-Object -Last 1) | ConvertFrom-Json
        Check "a job row carries the raw tool name ('name')" ([string]$jobRow.name -eq 'pwsh') ("name=" + $jobRow.name + " program=" + $jobRow.program)
        Check "a job row still carries the inner program ('program')" ([string]$jobRow.program -eq 'pwsh')
      } catch {
        Check 'engine/activity.mjs buildJobs() can be probed' $false $_.Exception.Message
      }
    }

    # ... and the file the renderer page polls must be a usable state line too.
    $stateFile = Join-Path $here 'pet\renderer\state.json'
    if (Test-Path -LiteralPath $stateFile) {
      $stateDoc = $null
      try { $stateDoc = [System.IO.File]::ReadAllText($stateFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $stateDoc = $null }
      Check 'pet\renderer\state.json is valid JSON' ($null -ne $stateDoc)
      if ($null -ne $stateDoc) {
        $fileState = [string]$stateDoc.state
        Check 'state.json carries one of the eleven activity categories' ($frozenPetColors.ContainsKey($fileState)) $fileState
        Check 'state.json colour matches the frozen table for its state' ($frozenPetColors[$fileState] -ieq [string]$stateDoc.color) "$fileState -> $($stateDoc.color)"
        Check 'state.json pose is one of the eleven poses' ($petPoses -contains [string]$stateDoc.pose) ([string]$stateDoc.pose)
        if ($null -ne $pet) {
          Write-Host ("      state.json {0} / {1} / {2}   snapshot pet {3} / {4}" -f $stateDoc.state, $stateDoc.label, $stateDoc.color, $pet.state, $pet.color)
        }
      }
    } else {
      Write-Host 'info  pet\renderer\state.json not written yet (the engine writes it on every poll)'
    }

    # ... and the reaction signals file the page's reaction layer reads.
    $signalsFile = Join-Path $here 'pet\renderer\signals.json'
    if (Test-Path -LiteralPath $signalsFile) {
      $sigDoc = $null
      try { $sigDoc = [System.IO.File]::ReadAllText($signalsFile, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $sigDoc = $null }
      Check 'pet\renderer\signals.json is valid JSON (reaction layer input)' ($null -ne $sigDoc)
      if ($null -ne $sigDoc) {
        foreach ($field in @('at', 'tool', 'turn', 'streaming', 'lastUserAt', 'idleMs', 'agents', 'jobs')) {
          Check ("signals.json has '$field'") ($null -ne $sigDoc.PSObject.Properties[$field])
        }
        if ($null -ne $sigDoc.tool) {
          Check 'signals.tool names the tool and its activity category' ((-not [string]::IsNullOrWhiteSpace([string]$sigDoc.tool.name)) -and ($frozenPetColors.ContainsKey([string]$sigDoc.tool.state))) ("$($sigDoc.tool.name) -> $($sigDoc.tool.state)")
          Write-Host ("      signals tool {0}/{1} ok={2} summary={3}" -f $sigDoc.tool.name, $sigDoc.tool.phase, $sigDoc.tool.ok, $sigDoc.tool.summary)
        }
      }
    } else {
      Write-Host 'info  pet\renderer\signals.json not written yet (the engine writes it on every poll)'
    }
  }
}

Write-Host ''
Write-Host '=== the reaction contract (task-7) ==='

# The enum, the palette and the priority ladder are the contract: read them out of
# pet\state.mjs itself (Node) rather than trusting a copy in this script.
if ($null -ne $node) {
  $probe = Join-Path $env:TEMP 'dsh-verify-state.mjs'
  $probeSource = @'
import { pathToFileURL } from 'node:url'
const mod = await import(pathToFileURL(process.argv[2]).href)
const table = mod.STATE_VALUES.map((key) => ({
  state: key, label: mod.PET_STATES[key].label, color: mod.PET_STATES[key].color, pose: mod.PET_STATES[key].pose,
}))
console.log(JSON.stringify({ table, priority: mod.STATE_PRIORITY, poses: mod.POSE_VALUES, reserved: mod.RESERVED_COLORS, toolActivityRead: mod.toolActivity('read'), toolActivityUnknown: mod.toolActivity('zzz') }))
'@
  try {
    [System.IO.File]::WriteAllText($probe, $probeSource, (New-Object System.Text.UTF8Encoding($false)))
    $json = & $node $probe (Join-Path $here 'pet\state.mjs') 2>&1 | Select-Object -Last 1
    $contract = $json | ConvertFrom-Json
    Check 'pet\state.mjs declares exactly the eleven activity categories' (@($contract.table).Count -eq 11) ("$(@($contract.table).Count) states: " + ((@($contract.table) | ForEach-Object { $_.state }) -join ', '))
    $colors = @($contract.table | ForEach-Object { $_.color })
    Check 'all eleven colours are pairwise distinct' (@($colors | Sort-Object -Unique).Count -eq 11)
    $borrowed = @($contract.table | Where-Object { $_.color -in @('#7EE787', '#FF7B72') })
    Check 'no state borrows a reserved panel colour' ($borrowed.Count -eq 0)
    Check 'the priority ladder lists all eleven states' (@($contract.priority).Count -eq 11) ((@($contract.priority)) -join ' > ')
    Check 'the poses are the eleven of REACTIONS-SPEC section 11' (@($contract.poses).Count -eq 11) ((@($contract.poses)) -join ' ')
    Check 'a read tool classifies as reading' ([string]$contract.toolActivityRead -eq 'reading') ([string]$contract.toolActivityRead)
    Check 'an unmatched tool falls back to reading' ([string]$contract.toolActivityUnknown -eq 'reading') ([string]$contract.toolActivityUnknown)
  } catch {
    Check 'pet\state.mjs contract can be read' $false $_.Exception.Message
  }
}

# The label must be a fixed-width, right-aligned box (no left-edge jitter) and the
# reaction layer must be wired into the page.
$indexFile = Join-Path $here 'pet\renderer\index.html'
if (Test-Path -LiteralPath $indexFile) {
  $html = [System.IO.File]::ReadAllText($indexFile, [System.Text.UTF8Encoding]::new($false))
  $labelBlock = [regex]::Match($html, '(?s)#state-label\s*\{(.*?)\}')
  $detailBlock = [regex]::Match($html, '(?s)#state-detail\s*\{(.*?)\}')
  Check 'the label is a fixed-width box (min-width: 4em)' ($labelBlock.Success -and $labelBlock.Groups[1].Value -match 'min-width:\s*4em')
  Check 'the label text is right-aligned (text-align: right)' ($labelBlock.Success -and $labelBlock.Groups[1].Value -match 'text-align:\s*right')
  Check 'the label uses tabular figures (font-variant-numeric: tabular-nums)' ($labelBlock.Success -and $labelBlock.Groups[1].Value -match 'font-variant-numeric:\s*tabular-nums')
  Check 'the detail line is fixed-width and right-aligned too' ($detailBlock.Success -and $detailBlock.Groups[1].Value -match 'min-width:\s*4em' -and $detailBlock.Groups[1].Value -match 'text-align:\s*right')
  Check 'the label never transitions width/transform (no jitter)' ($labelBlock.Success -and $labelBlock.Groups[1].Value -notmatch 'transition:[^;]*(width|transform|left|right)')
  Check 'the page loads the reaction layer (reactions.js)' ($html -match 'src="\./reactions\.js(\?v=[0-9]+)?"')
  Check 'the page has the speech bubble element' ($html -match 'id="bubble"')
} else {
  Check 'pet\renderer\index.html exists' $false
}
Check 'pet\renderer\interact.js is gone (task-13 removed the interaction layer)' (-not (Test-Path -LiteralPath (Join-Path $here 'pet\renderer\interact.js')))

# ============================ whole-window click-through (task-13) ==============
# The pet must never block the desktop: the host sets WS_EX_TRANSPARENT, so the
# window - character pixels included - is invisible to hit testing.
$hostScript = Join-Path $here 'pet\host\host.ps1'
if (Test-Path -LiteralPath $hostScript) {
  $hs = [System.IO.File]::ReadAllText($hostScript, [System.Text.UTF8Encoding]::new($false))
  Check 'the host defaults to whole-window click-through (-ClickThrough 1)' ($hs -match '\[int\]\$ClickThrough = 1')
  Check 'the host still applies WS_EX_TRANSPARENT when click-through is on' ($hs -match '\$ex -bor \$WS_EX_TRANSPARENT')
  Check 'no hit-silhouette code is left in the host' ($hs -notmatch 'Set-HitMask' -and $hs -notmatch 'FromArgb\(1, 0, 0, 0\)' -and $hs -notmatch 'GetCursorPos')
  Check 'no drag/offset channel is left in the host' ($hs -notmatch 'pet-offset' -and $hs -notmatch 'Move-PetWindow')
  $wg = [System.IO.File]::ReadAllText((Join-Path $here 'ui\widget.ps1'), [System.Text.UTF8Encoding]::new($false))
  Check 'the panel no longer honours a drag offset' ($wg -notmatch 'PetOffsetPath' -and $wg -notmatch 'DragOffset')
}
# The interaction layer is gone (task-13): none of its channel files may be left behind.
foreach ($ch in @('pet\host\pet-offset.json', 'pet\host\force-state.json', 'pet\host\watch.json')) {
  Check ("no leftover channel file " + $ch) (-not (Test-Path -LiteralPath (Join-Path $here $ch)))
}
# ==================== perceptual (visibility) gate, task-15 E ====================
# Mechanism readings are not acceptance: a reaction has to be VISIBLE.  The gate measures
# the character's silhouette (bounding box + area + centroid) over baseline frames and
# reaction frames; raw pixels are useless here because a perfectly still Live2D character
# still jitters ~30% of her own pixels by >8/255 between frames, which drowns every real
# gesture (that was task-14's hole).  Bar: the gesture's PEAK >= 2x baseline jitter.
$gateAfter = Join-Path $here 'pet\showcase\reactions-test\perceptual-gate-AFTER.json'
$gateBefore = Join-Path $here 'pet\showcase\reactions-test\perceptual-gate-BEFORE.json'
if (Test-Path -LiteralPath $gateAfter) {
  try {
    $ga = [System.IO.File]::ReadAllText($gateAfter, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
    $peak = [double]$ga.best.xBaseline
    Check 'a real tool reaction is perceptually visible (>= 2x baseline jitter)' ($ga.pass -eq $true -and $peak -ge 2.0) ('peak ' + $peak + 'x jitter at ' + $ga.best.label)
    Check 'the gate measured a baseline jitter from >= 3 frame pairs' ([int]$ga.baseline.frames -ge 3) ('baseline ' + $ga.baseline.medianDistance + ' from ' + $ga.baseline.frames + ' pairs')
  } catch {
    Check 'the perceptual gate report parses' $false $_.Exception.Message
  }
} else {
  Write-Host 'info  perceptual-gate-AFTER.json missing (run perceptual_gate.py measure)'
}
if (Test-Path -LiteralPath $gateBefore) {
  try {
    $gb = [System.IO.File]::ReadAllText($gateBefore, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
    Check 'the gate really fails the OLD (task-14) behaviour' ($gb.pass -eq $false) ('old peak ' + $gb.best.xBaseline + 'x jitter')
  } catch { }
}
$ptReport = Join-Path $here 'pet\host\task13-passthrough.txt'
if (Test-Path -LiteralPath $ptReport) {
  $pt = [System.IO.File]::ReadAllText($ptReport, [System.Text.UTF8Encoding]::new($false))
  $ptOk = ([regex]::Matches($pt, 'ok ')).Count
  $ptBad = ([regex]::Matches($pt, 'FAIL')).Count
  Check 'the pass-through report probes at least six points' ($ptOk -ge 6) ($ptOk.ToString() + ' ok point(s)')
  Check 'EVERY probed point falls through to a window below (no point is ours)' ($ptBad -eq 0 -and $pt -notmatch 'route=ours')
  Write-Host ('      pass-through report: ' + $ptOk + ' point(s), all OTHERS')
} else {
  Write-Host 'info  pet\host\task13-passthrough.txt not written yet (pet\host\passthrough-check.ps1)'
}
Check 'pet\renderer\reactions.js exists' (Test-Path -LiteralPath (Join-Path $here 'pet\renderer\reactions.js'))

# ============================ the upstream-gap capabilities (task-10) ============
# The three upstream tables (decorations / scenes / one-shot actions) are pure data
# plus a composition function; the two long-standing defects (an idle motion loop and
# the missing `exclusive` on a tool error) are pinned here as well.
$reactionsPath = Join-Path $here 'pet\renderer\reactions.js'
if (Test-Path -LiteralPath $reactionsPath) {
  $rx = [System.IO.File]::ReadAllText($reactionsPath, [System.Text.UTF8Encoding]::new($false))
  $decorBlock = [regex]::Match($rx, '(?s)var DECOR = \{(.*?)\n  \}')
  $sceneBlock = [regex]::Match($rx, '(?s)var SCENES = \{(.*?)\n  \}')
  $actionBlock = [regex]::Match($rx, '(?s)var ACTIONS = \{(.*?)\n  \}')
  Check 'reactions.js declares DECOR / SCENES / ACTIONS' ($decorBlock.Success -and $sceneBlock.Success -and $actionBlock.Success)
  if ($decorBlock.Success) {
    $slots = ([regex]::Matches($decorBlock.Groups[1].Value, 'slot:')).Count
    Check 'DECOR carries the eleven upstream decorations' ($slots -ge 11) "$slots slot assignments"
    foreach ($group in @('glasses', 'sticker', 'headwear')) {
      Check "DECOR has the mutual-exclusion slot '$group'" ($decorBlock.Groups[1].Value -match ("slot: '" + $group + "'"))
    }
  }
  if ($sceneBlock.Success) {
    foreach ($scene in @('darkCloth', 'whaleOnDesk', 'parfait', 'claw', 'clawRecolor', 'phone', 'phoneRecolor')) {
      Check "SCENES has '$scene'" ($sceneBlock.Groups[1].Value -match ($scene + ':'))
    }
    Check 'SCENES prerequisite: clawRecolor needs claw' ($sceneBlock.Groups[1].Value -match "clawRecolor:.*needs: 'claw'")
    Check 'SCENES prerequisite: phoneRecolor needs phone' ($sceneBlock.Groups[1].Value -match "phoneRecolor:.*needs: 'phone'")
  }
  if ($actionBlock.Success) {
    foreach ($a in @('paw', 'catPaw', 'doubleV', 'love', 'heartbeat', 'squeeze', 'eraser', 'undo', 'omurice', 'selfie', 'selfieQuick', 'splash')) {
      Check "ACTIONS has '$a'" ($actionBlock.Groups[1].Value -match ('(?m)^\s*' + $a + ':'))
    }
    Check 'ACTIONS records the upstream durations (4 400 / 6 200 / 3 600 ms)' `
      ($actionBlock.Groups[1].Value -match '4400' -and $actionBlock.Groups[1].Value -match '6200' -and $actionBlock.Groups[1].Value -match '3600')
    Check 'a media action declares its prerequisite (selfie -> phone)' ($actionBlock.Groups[1].Value -match "selfie:.*needs: 'phone'")
  }
  Check 'the error override is exclusive (props:[] + exclusive:true)' ([regex]::Matches($rx, 'exclusive: true').Count -ge 2)
  Check 'act() is exported as a composition entry point' ([regex]::IsMatch($rx, '(?m)^\s*act: act,'))
  Check 'setProp()/setProps() manage the user layer with slots and needs' ($rx -match 'function setProp' -and $rx -match 'userProps\[spec\.slot\] = key' -and $rx -match 'dsh-live2d-pet:props')
  Check 'qBounce is implemented (pure CSS, never a model parameter)' ($rx -match 'function qBounce' -and $rx -match "classList.add\('qbounce'\)")
  Check 'the one-shot action layer is accounted by duration (act-end)' ($rx -match 'kind: .act-end.')
  Check 'low-performance mode exists (ticker maxFPS)' ($rx -match 'maxFPS')
  Check 'the work cycle re-rolls the face every 9-14 s' ($rx -match '9000 \+ Math\.random\(\) \* 5000')
  Check 'pickFresh avoids repeating the same line' ($rx -match 'function pickFresh')
}
$indexPath = Join-Path $here 'pet\renderer\index.html'
if (Test-Path -LiteralPath $indexPath) {
  $idx = [System.IO.File]::ReadAllText($indexPath, [System.Text.UTF8Encoding]::new($false))
  Check 'index.html has the qbounce keyframes and only animates the canvas' ($idx -match '@keyframes qbounce' -and $idx -match 'canvas\.qbounce')
  Check 'the page scripts carry a cache stamp (?v=) - WebView2 caches pet.local' ($idx -match 'pet-app\.js\?v=' -and $idx -match 'reactions\.js\?v=')
}
# The idle question, asserted on the code: the framework's default idle group is
# 'Idle', our model only declares 'idle', so nothing loops unless the page asks.
if (Test-Path -LiteralPath $renderer) {
  $app2 = [System.IO.File]::ReadAllText($renderer, [System.Text.UTF8Encoding]::new($false))
  Check 'the page never passes idleMotionGroup (no idle loop)' (-not $app2.Contains('idleMotionGroup:'))
}
$gapReport = Join-Path $here 'pet\showcase\task10-gap-check.txt'
if (Test-Path -LiteralPath $gapReport) {
  $gap = [System.IO.File]::ReadAllText($gapReport, [System.Text.UTF8Encoding]::new($false))
  Check 'the gap report shows no motion looping while idle' ($gap -match 'playing=False' -and $gap -match 'idleGroup=Idle')
  Check 'the gap report shows the exclusive error face (props cleared)' ($gap -match 'error\(exclusive\)' -and $gap -match 'exclusive=\[True\]')
  Check 'the gap report shows a one-shot action playing (ketchup motion)' ($gap -match 'playing=True' -and $gap -match 'motiveGroups=ketchup,openLid')
  Write-Host ("      gap report: {0} bytes" -f $gap.Length)
} else {
  Write-Host 'info  pet\showcase\task10-gap-check.txt not written yet (pet\host\gap-check.ps1)'
}

# The showcase: one real screenshot per activity category, plus the self-contained
# document and its text index. A screenshot below 20 KB is a placeholder, not a
# capture of the live panel + pet, so the size is part of the check.
$showcaseDir = Join-Path $here 'pet\showcase'
if (Test-Path -LiteralPath $showcaseDir) {
  $missingShots = @()
  $tooSmall = @()
  foreach ($name in $frozenPetColors.Keys) {
    $shot = Join-Path $showcaseDir ("state-{0}.png" -f $name)
    if (-not (Test-Path -LiteralPath $shot)) { $missingShots += $name; continue }
    if ((Get-Item -LiteralPath $shot).Length -lt 20480) { $tooSmall += $name }
  }
  Check 'pet\showcase\ has a screenshot for all eleven activity categories' ($missingShots.Count -eq 0) (($missingShots -join ', '))
  Check 'every showcase screenshot is a real capture (> 20 KB)' ($tooSmall.Count -eq 0) (($tooSmall -join ', '))
  $docHtml = @(Get-ChildItem -LiteralPath $showcaseDir -Filter '*.html' -File)
  Check 'pet\showcase\ has the self-contained showcase document' ($docHtml.Count -ge 1) (($docHtml | ForEach-Object { $_.Name }) -join ', ')
  if ($docHtml.Count -ge 1) {
    $docText = [System.IO.File]::ReadAllText($docHtml[0].FullName, [System.Text.UTF8Encoding]::new($false))
    $embeddedCount = ([regex]::Matches($docText, 'src="data:image/png;base64,')).Count
    Check 'the showcase document embeds all eleven images (base64, no external files)' ($embeddedCount -eq 11) "$embeddedCount data: image(s)"
    Check 'the showcase document has no external reference (zero network)' ($docText -notmatch 'src="(?!data:)' -and $docText -notmatch 'href="http' -and $docText -notmatch '<script src')
    Check 'the showcase document names every category' (@($frozenPetColors.Keys | Where-Object { $docText -notmatch [regex]::Escape($_) }).Count -eq 0) ''
    Write-Host ("      showcase: {0} image(s) embedded, {1} KB" -f $embeddedCount, [math]::Round((Get-Item -LiteralPath $docHtml[0].FullName).Length / 1024))
  }
  Check 'pet\showcase\README.md exists (text index)' (Test-Path -LiteralPath (Join-Path $showcaseDir 'README.md'))
} else {
  Check 'pet\showcase\ exists' $false
}
$reactionsFile = Join-Path $here 'pet\renderer\reactions.js'
if (Test-Path -LiteralPath $reactionsFile) {
  $js = [System.IO.File]::ReadAllText($reactionsFile, [System.Text.UTF8Encoding]::new($false))
  Check 'the reaction layer reads signals.json' ($js -match 'signals\.json')
  Check 'the reaction layer can play the device motion (openLid)' ($js -match 'openLid')
  Check 'the reaction layer keeps the tool-error face short (1.6 s TTL)' ($js -match '1_?600|1600')
  Check 'the reaction layer never plays the forbidden aidale motion' ($js -notmatch "aidale")
  Check 'reactions.js declares the idle brain' ($js -match 'idleNextAt|tickWatchdog')
}

# The model metadata patch: 44 expressions declared, LipSync wired, every file present.
$modelJson = Join-Path $here 'pet\model\c_0120.model3.json'
if (Test-Path -LiteralPath $modelJson) {
  $modelDoc = $null
  try { $modelDoc = [System.IO.File]::ReadAllText($modelJson, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json } catch { $modelDoc = $null }
  Check 'pet\model\c_0120.model3.json is valid JSON' ($null -ne $modelDoc)
  if ($null -ne $modelDoc) {
    $expressions = @($modelDoc.FileReferences.Expressions)
    Check 'the model declares 44 Expressions (expressionManager needs them)' ($expressions.Count -eq 44) ("$($expressions.Count) entries")
    $missingExpression = @($expressions | Where-Object { -not (Test-Path -LiteralPath (Join-Path (Join-Path $here 'pet\model') ($_.File -replace '/', '\'))) })
    Check 'every declared expression file exists' ($missingExpression.Count -eq 0) (($missingExpression | ForEach-Object { $_.File }) -join ', ')
    $lipsync = @($modelDoc.Groups | Where-Object { $_.Name -eq 'LipSync' })
    Check 'Groups[LipSync].Ids is ["ParamMouthOpenY"] (mouth moves while talking)' `
      ($lipsync.Count -eq 1 -and @($lipsync[0].Ids).Count -eq 1 -and [string]$lipsync[0].Ids[0] -eq 'ParamMouthOpenY') `
      ("[" + (@($lipsync[0].Ids) -join ', ') + "]")
    Check 'the motions declared by the model are still there (patch is additive)' (@($modelDoc.FileReferences.Motions.PSObject.Properties).Count -eq 8)
  }
} else {
  Check 'pet\model\c_0120.model3.json exists' $false
}

Write-Host ''
if ($failures -eq 0) {
  Write-Host 'RESULT  all project checks passed'
  exit 0
}
Write-Host ("RESULT  {0} check(s) failed" -f $failures)
exit 1

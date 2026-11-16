<#
.SYNOPSIS
Register (or remove) the start-up entry for the usage widget.

.DESCRIPTION
The widget is a standalone program that lives alongside DeepSeek Harness: it
starts at logon, waits for the DSH process to appear, shows itself while the app
is running, and hides again when the app exits. The association itself is inside
the widget, so all this script does is make the widget start at logon.

**There is deliberately no `.cmd` or `.bat` launcher.** The first version of this
project shipped one, and 火绒 (Huorong) quarantined it as a trojan: a batch file
whose body runs PowerShell hidden, with the execution policy bypassed, is the
classic defence-evasion shape and deserves that heuristic. This installer
therefore uses only boring pieces:

  * a per-user **logon scheduled task** whose action is plain
    `powershell.exe -NoProfile -File "<...>\ui\widget.ps1"`, and
  * a **Start Menu shortcut** with the same command, for starting it by hand.

No `-WindowStyle Hidden`, no `-ExecutionPolicy Bypass`, no encoded command
anywhere — the widget hides its own console from inside instead.

No elevation is needed: both the task and the shortcut belong to the current
interactive user.

.PARAMETER Uninstall
Remove the logon task and the shortcut instead of creating them.
#>
[CmdletBinding()]
param(
  [switch]$Uninstall,
  [string]$TaskName = 'DshUsageWidget',
  [string]$ShortcutName = 'DSH Usage Widget'
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$entry = Join-Path $here 'ui\widget.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Programs')) "$ShortcutName.lnk"

if ($Uninstall) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed the logon task
Unregister-ScheduledTask -TaskName 'DshUsageWidgetWatchdog' -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed the watchdog task 'DshUsageWidgetWatchdog'" '$TaskName'"
  } else {
    Write-Host "no logon task named '$TaskName'"
  }
  if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Host "removed the shortcut '$shortcutPath'"
  }
  return
}

if (-not (Test-Path -LiteralPath $entry)) { throw "widget entry point not found: $entry" }
if (-not (Test-Path -LiteralPath $powershell)) { throw "powershell not found: $powershell" }

$arguments = '-NoProfile -File "{0}"' -f $entry

# 1. the logon task --------------------------------------------------------
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $here

# At logon, and then once a minute as a safety net.
#
# The widget is single-instance (a named mutex makes a second copy exit at once),
# so the repeat costs nothing while it is running and revives it whenever it is
# not. It exists because of a real report: registering a logon task does not run
# it, so the first person to install this opened DeepSeek Harness, saw no widget,
# and reasonably concluded the two were not linked. The repeat closes that gap,
# and the explicit Start-ScheduledTask below closes it now rather than at the
# next sign-in.
# One trigger only: at logon. An earlier build also repeated a once-trigger every
# minute as a safety net, but that is the wrong shape for this task — its action
# *is* the widget, which never exits, so with `-MultipleInstances IgnoreNew` every
# repetition was refused and the task logged `0x80070420` ("already running") once
# a minute while sitting permanently in the running state. No benefit, one error a
# minute. The explicit Start-ScheduledTask below still starts it immediately, so
# installing does not require signing out.
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$triggers = @($logonTrigger)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "registered the logon task '$($task.TaskName)'  (state: $($task.State))"
Write-Host '  trigger: at logon only'

Start-ScheduledTask -TaskName $TaskName
Write-Host 'started it now, so you do not have to sign out before the widget exists'
  # 1b. the silent watchdog (task-17) ----------------------------------------
  # Every 4 minutes: start the widget task ONLY when the panel is not running, then exit.
  # The old "heal every minute" task was removed because it logged 0x41370420 ("task is
  # already running") every minute; this one finishes in a second, so a healthy period
  # leaves a clean result code 0. This is what turns "died once, dead for a week" into
  # "back within four minutes".
  $watchdogScript = Join-Path $here 'pet\host\watchdog.ps1'
  if (Test-Path -LiteralPath $watchdogScript) {
    $wdAction = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -File "' + $watchdogScript + '" -Quiet') -WorkingDirectory $here
    $wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(1) -RepetitionInterval (New-TimeSpan -Minutes 4)
    $wdSettings = New-ScheduledTaskSettingsSet `
      -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries `
      -StartWhenAvailable `
      -MultipleInstances IgnoreNew `
      -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    # task-18: the watchdog MUST be non-interactive (S4U). An interactive task's console
    # becomes visible the moment the script writes to stdout - that was the window the user
    # saw flashing every four minutes. Session 0 has no desktop, so S4U cannot show one.
    # The widget task itself stays Interactive on purpose: it has to draw the UI.
    $wdPrincipal = New-ScheduledTaskPrincipal -UserId $principal.UserId -LogonType S4U -RunLevel Limited
    Register-ScheduledTask -TaskName 'DshUsageWidgetWatchdog' -Action $wdAction -Trigger $wdTrigger `
      -Principal $wdPrincipal -Settings $wdSettings -Force | Out-Null
    Write-Host "registered the watchdog task 'DshUsageWidgetWatchdog' (non-interactive/S4U, every 4 minutes, starts the widget only when it is missing)"
  } else {
    Write-Host 'info  pet\host\watchdog.ps1 not found - no watchdog registered'
  }


# 2. the manual shortcut ---------------------------------------------------
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutPath)
$link.TargetPath = $powershell
$link.Arguments = $arguments
$link.WorkingDirectory = $here
$link.Description = 'Semi-transparent usage and spend widget for DeepSeek Harness'
$link.Save()
Write-Host "created the shortcut '$shortcutPath'"

Write-Host ''
Write-Host 'Both entries run exactly this, and nothing else:'
Write-Host "  $powershell $arguments"
Write-Host ''
Write-Host 'The widget waits for DeepSeek Harness to appear, so it stays hidden until'
Write-Host 'the app is running. Remove both entries again with:'
Write-Host "  powershell -NoProfile -File `"$PSCommandPath`" -Uninstall"

<#
.SYNOPSIS
Restart the packaged DeepSeek Harness desktop application and verify the
usage-dashboard plugin against the fresh process.

.DESCRIPTION
A plugin's HOST half is cached by Node's ESM registry, so an edit to it reaches
the running GUI only when the host process is replaced. The desktop application
is an Electron shell whose dsh host is a child process that owns the GUI port, so
the whole application is replaced here.

Launch this from OUTSIDE the application's process tree — for example through
WMI's Win32_Process.Create. Anything started inside the application is torn down
with it, which is exactly why the same work cannot be done from a tool call in an
agent session hosted by it.

.PARAMETER DelaySeconds
Wait this long before touching the application, so a caller can finish its turn.

.PARAMETER Port
Preferred GUI port. The port actually discovered after boot wins, because the
application may bind a different one.
#>
[CmdletBinding()]
param(
  [string]$App = 'D:\DeepSeek Harness\DeepSeek Harness.exe',
  [int]$Port = 19387,
  [int]$DelaySeconds = 0,
  [int]$BootTimeoutSeconds = 180,
  [string]$Log = '',
  [string]$RemoveTask = ''
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $here 'restart-report.txt' }
$Log = [System.IO.Path]::GetFullPath($Log)
$node = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'
$verify = Join-Path $here 'scripts\verify-live.mjs'
$liveReport = Join-Path $here 'live-report.txt'

function Say {
  param([string]$Line)
  $text = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Line
  Write-Host $text
  try { Add-Content -LiteralPath $Log -Value $text -Encoding UTF8 } catch { }
}

$session = [System.Diagnostics.Process]::GetCurrentProcess().SessionId
Say ('restart-app: begin  session={0}  app={1}  preferredPort={2}  delay={3}s' -f $session, $App, $Port, $DelaySeconds)

if ($DelaySeconds -gt 0) {
  Say "waiting $DelaySeconds s before touching the application"
  Start-Sleep -Seconds $DelaySeconds
}

# 1. stop every process of the application ---------------------------------
$before = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
Say ('stopping {0} application process(es): {1}' -f $before.Count, (($before | ForEach-Object { $_.Id }) -join ', '))
foreach ($process in $before) {
  try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { }
}

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  if (-not (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 500
}
Say ('stopped; {0} process(es) remain' -f @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue).Count)

# 2. start it again --------------------------------------------------------
Say "starting $App"
try {
  Start-Process -FilePath $App | Out-Null
} catch {
  Say "FAILED to start the application: $($_.Exception.Message)"
  exit 1
}

function Test-Http {
  param([int]$Candidate)
  try {
    Invoke-WebRequest -Uri "http://127.0.0.1:$Candidate/" -UseBasicParsing -TimeoutSec 3 | Out-Null
    return $true
  } catch {
    return ($null -ne $_.Exception.Response)
  }
}

# 3. discover the GUI port -------------------------------------------------
$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
$found = 0
while ((Get-Date) -lt $deadline) {
  $ids = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
  $candidates = @()
  foreach ($processId in $ids) {
    $candidates += @(Get-NetTCPConnection -State Listen -OwningProcess $processId -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty LocalPort)
  }
  $candidates = @($candidates | Sort-Object -Unique)
  if ($candidates -contains $Port) { $found = $Port; break }
  foreach ($candidate in $candidates) {
    if (Test-Http $candidate) { $found = $candidate; break }
  }
  if ($found -ne 0) { break }
  Start-Sleep -Seconds 2
}

if ($found -eq 0) {
  Say "FAILED: no GUI port answered within $BootTimeoutSeconds s; start the app from the Start Menu"
  exit 1
}
Say "GUI answering on http://127.0.0.1:$found/"

# 4. verify the plugin end to end -----------------------------------------
if (Test-Path -LiteralPath $verify) {
  Say 'running verify-live.mjs'
  & $node $verify --url "http://127.0.0.1:$found/" --log $liveReport 2>&1 | ForEach-Object { Say ('  | ' + $_) }
  Say ('verify-live exit code {0}' -f $LASTEXITCODE)
} else {
  Say "FAILED: verifier not found at $verify"
}

if ($RemoveTask -ne '') {
  try {
    Unregister-ScheduledTask -TaskName $RemoveTask -Confirm:$false -ErrorAction Stop
    Say "removed the one-shot task $RemoveTask"
  } catch {
    Say "could not remove the one-shot task $RemoveTask : $($_.Exception.Message)"
  }
}

Say 'restart-app: done'

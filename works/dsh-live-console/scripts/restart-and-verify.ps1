<#
.SYNOPSIS
Restart the packaged DeepSeek Harness app and verify the dsh-live-console plugin.

.DESCRIPTION
The host half of the plugin is cached by the Loader for the life of the process,
and the client half is only scanned when the composition is built. A source or
`dsh.client` change therefore needs the application restarted, which is what this
script does.

Run it from OUTSIDE the application's process tree (a normal terminal, Task
Scheduler, or WMI) - it kills every "DeepSeek Harness.exe" process, including the
one hosting the agent session that may have started it.

After reboot it waits for the plugin to rewrite `$DSH_HOME\live-console\url.txt`,
then probes the page and `/live-console/state` over HTTP and prints a summary.
The URL key is persisted, so the console URL stays the same across restarts.

.PARAMETER DelaySeconds
Wait this long before stopping the application, so a caller can finish its turn.
#>
[CmdletBinding()]
param(
  [string]$App = 'D:\DeepSeek Harness\DeepSeek Harness.exe',
  [int]$DelaySeconds = 0,
  [int]$BootTimeoutSeconds = 180,
  [string]$Log = ''
)

$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Log)) { $Log = Join-Path $here 'restart-console-report.txt' }
$Log = [System.IO.Path]::GetFullPath($Log)
$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
$urlFile = Join-Path $dshHome 'live-console\url.txt'
$keyFile = Join-Path $dshHome 'live-console\key.txt'

function Say {
  param([string]$Line)
  $text = '[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'), $Line
  Write-Host $text
  try { Add-Content -LiteralPath $Log -Value $text -Encoding UTF8 } catch { }
}

Say 'restart-console: begin'
if ($DelaySeconds -gt 0) {
  Say ("waiting {0}s before touching the application" -f $DelaySeconds)
  Start-Sleep -Seconds $DelaySeconds
}

$oldKey = if (Test-Path -LiteralPath $keyFile) { (Get-Content -LiteralPath $keyFile -Raw).Trim() } else { '' }
$oldUrl = if (Test-Path -LiteralPath $urlFile) { (Get-Content -LiteralPath $urlFile -Raw).Trim() } else { '' }

# 1) stop the whole application
$before = @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
Say ('stopping {0} application process(es)' -f $before.Count)
foreach ($process in $before) {
  try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { }
}
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  if (-not (Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 500
}
Say ('stopped; {0} process(es) remain' -f @(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue).Count)

# 2) start it again
$startedAt = Get-Date
Say "starting $App"
try {
  Start-Process -FilePath $App | Out-Null
} catch {
  Say ("FAILED to start the application: " + $_.Exception.Message)
  exit 1
}

# 3) wait for the plugin to publish a fresh console URL
$deadline = (Get-Date).AddSeconds($BootTimeoutSeconds)
$url = ''
while ((Get-Date) -lt $deadline) {
  if (Test-Path -LiteralPath $urlFile) {
    try {
      $info = Get-Item -LiteralPath $urlFile
      $content = (Get-Content -LiteralPath $urlFile -Raw).Trim()
      if ($content.Length -gt 0 -and $info.LastWriteTime -ge $startedAt.AddSeconds(-3)) {
        $url = $content
        break
      }
    } catch { }
  }
  Start-Sleep -Seconds 2
}
if ($url.Length -eq 0) {
  Say 'FAILED: the console URL file was not rewritten within the boot timeout'
  Say 'Start the app from the Start Menu and check that dsh-live-console is still in dsh.profile.bundles.'
  exit 1
}
Say "console url: $url"
$newKey = if (Test-Path -LiteralPath $keyFile) { (Get-Content -LiteralPath $keyFile -Raw).Trim() } else { '' }
if ($oldKey.Length -gt 0 -and $newKey.Length -gt 0 -and $oldKey -eq $newKey) {
  Say 'access key preserved across restart (the old browser tab can reconnect)'
} else {
  Say 'access key changed; open the URL above'
}

# 4) probe the page and state
$pageDeadline = (Get-Date).AddSeconds(90)
$pageOk = $false
while ((Get-Date) -lt $pageDeadline) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
      $pageOk = $true
      Say ('page OK ({0} bytes)' -f $response.Content.Length)
      break
    }
  } catch { }
  Start-Sleep -Seconds 2
}
if (-not $pageOk) {
  Say 'FAILED: the console page did not answer 200'
  exit 1
}

$stateUrl = $url -replace '/live-console\?', '/live-console/state?'
try {
  $state = Invoke-RestMethod -Uri $stateUrl -TimeoutSec 20
  Say ('state OK: sessions={0} jobs={1} events={2} clients={3}' -f @($state.sessions).Count, @($state.jobs).Count, @($state.events).Count, $state.stats.clients)
  if ($null -ne $state.usage) {
    if ($state.usage.enabled -eq $true) {
      $total = $state.usage.totals
      Say ('usage OK: enabled, sweeping={0}, totalCostUsd={1}, calls={2}' -f $state.usage.sweeping, $total.costUsd, $total.calls)
      if ($null -ne $state.usage.balance -and $state.usage.balance.ok -eq $true) {
        Say ('balance OK: {0} {1}' -f $state.usage.balance.currency, $state.usage.balance.total)
      }
    } else {
      Say 'usage is disabled by config'
    }
  }
} catch {
  Say ('state probe failed: ' + $_.Exception.Message)
}

Say 'Check the conversation header for the console action; it is registered by the client half.'
Say 'restart-console: done'

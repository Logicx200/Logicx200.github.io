# One-shot headless browser probe: launch, write stdout/stderr to files, report exit.
#
# ASCII ONLY. PowerShell 5.1 parses .ps1 as the system ANSI code page unless the
# file carries a UTF-8 BOM; a non-ASCII character can silently break the parser.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/probe-browser.ps1 `
#       -Exe <path> -OutDir <dir> -Url <url> [-Screenshot <png>] [-VirtualTimeMs 20000] [-TimeoutSec 90]

param(
  [Parameter(Mandatory = $true)][string]$Exe,
  [Parameter(Mandatory = $true)][string]$OutDir,
  [Parameter(Mandatory = $true)][string]$Url,
  [string]$Screenshot = '',
  [int]$VirtualTimeMs = 20000,
  [int]$TimeoutSec = 90,
  [int]$WindowW = 1400,
  [int]$WindowH = 900
)

$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$profile = Join-Path $env:TEMP ('stc-probe-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $profile | Out-Null

$bargs = @(
  '--headless=new',
  '--disable-gpu-sandbox',
  '--no-sandbox',
  '--disable-crash-reporter',
  '--no-crash-upload',
  '--disable-breakpad',
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-extensions',
  '--disable-sync',
  '--hide-scrollbars',
  "--user-data-dir=$profile",
  "--window-size=$WindowW,$WindowH",
  '--force-device-scale-factor=1',
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--allow-file-access-from-files',
  '--disable-features=Translate,MediaRouter,OptimizationHints'
)

if ($Screenshot -ne '') {
  $bargs += "--screenshot=$Screenshot"
}
if ($VirtualTimeMs -gt 0) {
  $bargs += "--virtual-time-budget=$VirtualTimeMs"
}
$bargs += '--dump-dom'
$bargs += $Url

$outFile = Join-Path $OutDir 'stdout.txt'
$errFile = Join-Path $OutDir 'stderr.txt'
$domFile = Join-Path $OutDir 'dom.html'

$t0 = Get-Date
$p = Start-Process -FilePath $Exe -ArgumentList $bargs -PassThru -NoNewWindow `
  -RedirectStandardOutput $outFile -RedirectStandardError $errFile

$exited = $p.WaitForExit($TimeoutSec * 1000)
$elapsed = [int]((Get-Date) - $t0).TotalMilliseconds

$lines = @(
  "exe=$Exe",
  "profile=$profile",
  "exited=$exited",
  "elapsed_ms=$elapsed",
  "exit_code=$(if ($exited) { $p.ExitCode } else { 'N/A' })",
  "screenshot_arg=$Screenshot",
  "screenshot_exists=$(if ($Screenshot -ne '') { Test-Path $Screenshot } else { 'n/a' })"
)
if ($Screenshot -ne '' -and (Test-Path $Screenshot)) {
  $lines += "screenshot_bytes=$((Get-Item $Screenshot).Length)"
}
$lines += "stdout_bytes=$(if (Test-Path $outFile) { (Get-Item $outFile).Length } else { 0 })"
$lines += "stderr_bytes=$(if (Test-Path $errFile) { (Get-Item $errFile).Length } else { 0 })"

Set-Content -Path (Join-Path $OutDir 'result.txt') -Value $lines -Encoding UTF8
Set-Content -Path (Join-Path $OutDir 'profile.txt') -Value $profile -Encoding UTF8

if (-not $exited) {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$profile*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# keep stdout as the DOM if the browser wrote it there
if ((Test-Path $outFile) -and ((Get-Item $outFile).Length -gt 0)) {
  Copy-Item $outFile $domFile -Force
}

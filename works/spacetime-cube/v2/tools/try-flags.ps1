# Try several flag combinations to see whether ANY headless Chromium can start.
# Each attempt is written up as one line so the whole matrix is easy to read.
#
# ASCII ONLY (Windows PowerShell 5.1 parses .ps1 as the system ANSI code page
# unless the file has a UTF-8 BOM).

param(
  [string]$OutDir = 'test/probe',
  [string]$Url = 'http://127.0.0.1:8731/index.html?demo=./sample/frame_%03d.png&n=24&hold=1',
  [int]$VirtualTimeMs = 15000
)

$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$exes = @(
  @{ name = 'msedge';     path = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' },
  @{ name = 'msedge-wv2'; path = '' }
)
$wv = Get-ChildItem 'C:\Program Files (x86)\Microsoft\EdgeWebView\Application' -Directory -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending | Select-Object -First 1
if ($wv) {
  $p = Join-Path $wv.FullName 'msedgewebview2.exe'
  if (Test-Path $p) { $exes[1].path = $p }
}

$base = @(
  '--headless=new',
  '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--disable-sync', '--hide-scrollbars',
  '--disable-crash-reporter', '--no-crash-upload', '--disable-breakpad',
  '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
  '--allow-file-access-from-files',
  '--window-size=1200,800', '--force-device-scale-factor=1'
)

$variants = @(
  @{ name = 'A-plain';              extra = @() },
  @{ name = 'B-nosandbox';          extra = @('--no-sandbox', '--disable-gpu-sandbox') },
  @{ name = 'C-nosandbox-ipc';      extra = @('--no-sandbox', '--disable-gpu-sandbox', '--disable-features=NetworkServiceSandbox,MojoIpcz', '--enable-features=NetworkServiceInProcess') },
  @{ name = 'D-inprocess-gpu';      extra = @('--no-sandbox', '--in-process-gpu', '--disable-features=NetworkServiceSandbox') },
  @{ name = 'E-inprocess-renderer'; extra = @('--no-sandbox', '--in-process-gpu', '--single-process', '--disable-features=NetworkServiceSandbox') },
  @{ name = 'F-swiftshader-only';   extra = @('--no-sandbox', '--disable-gpu', '--enable-unsafe-swiftshader') },
  @{ name = 'G-disable-ipc-feats';  extra = @('--no-sandbox', '--disable-features=NetworkServiceSandbox,MojoIpcz,UseMojoIpcForBrowserInterfaceBroker') }
)

$rows = @()
foreach ($exe in $exes) {
  if ([string]::IsNullOrEmpty($exe.path)) { continue }
  foreach ($v in $variants) {
    foreach ($shot in @($false, $true)) {
      $tag = $exe.name + '/' + $v.name + $(if ($shot) { '/shot' } else { '/dom' })
      $profile = Join-Path $env:TEMP ('stc-m-' + [guid]::NewGuid().ToString('N'))
      New-Item -ItemType Directory -Force -Path $profile | Out-Null
      $png = Join-Path $OutDir ($tag.Replace('/', '_') + '.png')
      $outF = Join-Path $OutDir ($tag.Replace('/', '_') + '.out')
      $errF = Join-Path $OutDir ($tag.Replace('/', '_') + '.err')

      $a = $base + $v.extra + @("--user-data-dir=$profile")
      if ($shot) { $a += "--screenshot=$png" }
      if ($VirtualTimeMs -gt 0) { $a += "--virtual-time-budget=$VirtualTimeMs" }
      $a += '--dump-dom'
      $a += $Url

      $t0 = Get-Date
      $proc = Start-Process -FilePath $exe.path -ArgumentList $a -PassThru -NoNewWindow `
        -RedirectStandardOutput $outF -RedirectStandardError $errF
      $ok = $proc.WaitForExit(45000)
      $ms = [int]((Get-Date) - $t0).TotalMilliseconds
      if (-not $ok) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like "*$profile*" } |
          ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
      }

      $errText = ''
      if (Test-Path $errF) { $errText = Get-Content $errF -Raw -ErrorAction SilentlyContinue }
      $fatal = ''
      $m = [regex]::Match($errText, 'FATAL:[^\r\n]*')
      if ($m.Success) { $fatal = $m.Value }
      $domBytes = 0
      if (Test-Path $outF) { $domBytes = (Get-Item $outF).Length }
      $pngBytes = 0
      if (Test-Path $png) { $pngBytes = (Get-Item $png).Length }

      $rows += [pscustomobject]@{
        variant = $tag
        exited  = $ok
        ms      = $ms
        domB    = $domBytes
        pngB    = $pngBytes
        fatal   = $(if ($fatal) { $fatal.Substring(0, [Math]::Min(70, $fatal.Length)) } else { '' })
      }
      Remove-Item $profile -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

$rows | Format-Table -AutoSize | Out-String -Width 200 | Set-Content (Join-Path $OutDir 'matrix.txt') -Encoding UTF8
$rows | Format-Table -AutoSize

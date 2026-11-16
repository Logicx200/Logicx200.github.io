# make-dist.ps1 -- EXPERIMENT A helper: build a MINIMAL Electron runtime directory that does NOT
# copy the 366 MB runtime.
#
# Idea: Windows symlinks work here without admin (verified on this box: New-Item -ItemType
# SymbolicLink succeeded), so `dist\DeepSeek Harness.exe` and every runtime payload file are
# symlinks back into D:\DeepSeek Harness\, `locales\` is a junction, and the ONLY real content is
# our own `resources\app\`. Electron must then resolve `resources` next to the SYMLINK (which is
# what we want) rather than next to the target -- that assumption is verified separately by
# probe-symlink.ps1 BEFORE anything is launched.
#
# PURE ASCII.
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dist = Join-Path $here 'dist'
$src = 'D:\DeepSeek Harness'

# payload Electron needs at runtime; the two dx* files are optional (WebGPU only) and the
# chromium licence html is not needed at runtime at all -- both kept out on purpose.
$files = @(
  'DeepSeek Harness.exe',
  'icudtl.dat', 'resources.pak', 'chrome_100_percent.pak', 'chrome_200_percent.pak',
  'snapshot_blob.bin', 'v8_context_snapshot.bin',
  'ffmpeg.dll', 'd3dcompiler_47.dll', 'vk_swiftshader.dll', 'vk_swiftshader_icd.json', 'vulkan-1.dll',
  'version', 'LICENSE.electron.txt'
)
$dirs = @('locales')

if ($Force -or -not (Test-Path $dist)) {
  if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $dist, (Join-Path $dist 'resources') | Out-Null

  foreach ($f in $files) {
    $target = Join-Path $src $f
    if (-not (Test-Path $target)) { Write-Host "SKIP (missing in source): $f"; continue }
    New-Item -ItemType SymbolicLink -Path (Join-Path $dist $f) -Target $target -Force | Out-Null
  }
  foreach ($d in $dirs) {
    $target = Join-Path $src $d
    if (-not (Test-Path $target)) { Write-Host "SKIP (missing in source): $d"; continue }
    New-Item -ItemType Junction -Path (Join-Path $dist $d) -Target $target -Force | Out-Null
  }
  # Electron falls back to default_app.asar + argv[1] only when resources\app.asar is ABSENT
  New-Item -ItemType SymbolicLink -Path (Join-Path $dist 'resources\default_app.asar') -Target (Join-Path $src 'resources\default_app.asar') -Force | Out-Null
}

# our own app (real files, tiny)
$appDst = Join-Path $dist 'resources\app'
if (Test-Path $appDst) { Remove-Item $appDst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $appDst | Out-Null
Copy-Item (Join-Path $here 'app\*') $appDst -Recurse -Force

# --- measure ---
$all = Get-ChildItem $dist -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer }
$apparent = ($all | Measure-Object Length -Sum).Sum
$real = ($all | Where-Object { -not $_.LinkType } | Measure-Object Length -Sum).Sum
$links = ($all | Where-Object { $_.LinkType }).Count
$junc = (Get-ChildItem $dist -Recurse -Force -Directory -ErrorAction SilentlyContinue | Where-Object { $_.LinkType }).Count
$fullCopy = (Get-ChildItem $src -File | Measure-Object Length -Sum).Sum + (Get-ChildItem (Join-Path $src 'locales') -File | Measure-Object Length -Sum).Sum

$report = [pscustomobject]@{
  dist = $dist
  symlinks = $links
  junctions = $junc
  realBytes = $real
  apparentBytes = $apparent
  fullCopyBytes = $fullCopy
  savedBytes = $fullCopy - $real
}
$report | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $here 'dist-cost.json') -Encoding UTF8
$report | Format-List
Write-Host ("real bytes on disk in dist : {0:N2} MB" -f ($real / 1MB))
Write-Host ("apparent (Explorer) size   : {0:N2} MB" -f ($apparent / 1MB))
Write-Host ("full-copy equivalent       : {0:N2} MB" -f ($fullCopy / 1MB))
Write-Host ("saved vs full copy         : {0:N2} MB" -f (($fullCopy - $real) / 1MB))

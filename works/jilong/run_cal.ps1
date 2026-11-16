# 并行跑 4 组 mu 标定
$base = 'F:\DeepSeek工作区\jilong\mf_cal'
$dirs = @('mu_080','mu_050','mu_030','mu_020')
foreach ($n in $dirs) {
    $d = Join-Path $base $n
    Write-Output "=== START $n  $(Get-Date -Format 'HH:mm:ss') ==="
    Set-Location $d
    & "$d\massflow.exe" *> "$d\stdout.log"
    Write-Output "=== DONE  $n  exit=$LASTEXITCODE  $(Get-Date -Format 'HH:mm:ss') ==="
}
Write-Output 'ALL CALIBRATION RUNS FINISHED'

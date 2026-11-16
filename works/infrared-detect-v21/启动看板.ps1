# 启动实时进度看板（端口 8766）
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $here "06_进度看板")
Write-Host "看板地址: http://localhost:8766/"
Write-Host "按 Ctrl+C 停止服务。"
python -m http.server 8766

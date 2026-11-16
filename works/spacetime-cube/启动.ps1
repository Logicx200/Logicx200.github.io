<#
  启动时空立方体的本地静态服务并打开浏览器。
  用法：  powershell -ExecutionPolicy Bypass -File .\启动.ps1
          powershell -ExecutionPolicy Bypass -File .\启动.ps1 -Port 8731
#>
param(
  [int]$Port = 8730,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://127.0.0.1:$Port/"

$node = Get-Command node -ErrorAction SilentlyContinue
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }

if ($node) {
  Write-Host "启动本地服务（Node）…" -ForegroundColor Cyan
  $job = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location $dir
    & node (Join-Path $dir 'server.js') $port
  } -ArgumentList $root, $Port
} elseif ($py) {
  Write-Host "启动本地服务（Python）…" -ForegroundColor Cyan
  $job = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location $dir
    & $using:py -m http.server $port --bind 127.0.0.1
  } -ArgumentList $root, $Port
} else {
  Write-Host "没有找到 Node 也没有找到 Python。" -ForegroundColor Red
  Write-Host "可以用 VS Code 的 Live Server 打开 index.html。"
  exit 1
}

# 等端口就绪
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
  try {
    $c = New-Object Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $Port)
    $c.Close()
    $ready = $true
    break
  } catch { Start-Sleep -Milliseconds 250 }
}

if (-not $ready) {
  Write-Host "服务没能在端口 $Port 上就绪。" -ForegroundColor Red
  Receive-Job $job
  exit 1
}

Write-Host "时空立方体  ->  $url" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $url }

Write-Host "按回车停止服务。"
[void](Read-Host)
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -Force -ErrorAction SilentlyContinue

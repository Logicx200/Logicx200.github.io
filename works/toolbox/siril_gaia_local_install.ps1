# ============================================================
#  Siril 1.4.x 本地 Gaia DR3 星表安装脚本（离线解析 + PCC 用）
#
#  作用：下载 Siril 官方 Gaia DR3 天体测量星表提取版（~1.14 GB 压缩），
#        校验、解压为 gaia_astrometric.dat（~1.5 GB），并给出 Siril 中的设置方法。
#        装好后：Plate Solving 和 光度色彩校准 (PCC) 都不再需要联网。
#
#  用法：在【普通 PowerShell 窗口】里（不是 DSH 里）执行：
#        powershell -ExecutionPolicy Bypass -File .\siril_gaia_local_install.ps1
#        可选参数：-TargetDir D:\SirilCatalog   -KeepArchive
#
#  数据来源：Zenodo record 14692304 "Siril Astrometry Catalogue extracted from Gaia DR3"
#            https://zenodo.org/records/14692304  (CC-BY-4.0)
# ============================================================
param(
    [string]$TargetDir = 'F:\SirilCatalog',
    [switch]$KeepArchive
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'Continue'

$url    = 'https://zenodo.org/records/14692304/files/siril_cat_healpix8_astro.dat.bz2?download=1'
$md5    = '2e62f2365023e621afbd336c82980208'
$sizeExp = 1142276749   # bytes, 来自 Zenodo API

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$bz2 = Join-Path $TargetDir 'siril_cat_healpix8_astro.dat.bz2'
$dat = Join-Path $TargetDir 'gaia_astrometric.dat'

Write-Host ""
Write-Host "目标目录 : $TargetDir" -ForegroundColor Cyan
Write-Host "文件大小 : 约 1.14 GB（解压后约 1.5 GB）" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 下载 ----------
if ((Test-Path $bz2) -and ((Get-Item $bz2).Length -eq $sizeExp)) {
    Write-Host "[1/3] 已存在完整压缩包，跳过下载。" -ForegroundColor Yellow
} else {
    Write-Host "[1/3] 开始下载（Zenodo 在国内可能较慢，可断点续传，中断后重跑本脚本即可）..." -ForegroundColor Green
    $curlArgs = @('-L','--fail','--retry','5','--retry-delay','5','-o',$bz2,$url)
    if (Test-Path $bz2) { $curlArgs = @('-C','-') + $curlArgs }   # 有残包则续传
    & curl.exe @curlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "下载失败（curl 退出码 $LASTEXITCODE）。可尝试：浏览器手动打开 $url 下载，保存到 $TargetDir 后重新运行本脚本。"
    }
}

# ---------- 2. 校验 ----------
Write-Host "[2/3] 校验 MD5 ..." -ForegroundColor Green
$got = (Get-FileHash -Path $bz2 -Algorithm MD5).Hash.ToLower()
if ($got -ne $md5) {
    throw "MD5 不匹配！`n  期望: $md5`n  实际: $got`n请删除 $bz2 后重试。"
}
Write-Host "      OK ($got)" -ForegroundColor Green

# ---------- 3. 解压（Python bz2，无需装 7-Zip） ----------
if (Test-Path $dat) {
    Write-Host "[3/3] 已存在 $dat，跳过解压。" -ForegroundColor Yellow
} else {
    Write-Host "[3/3] 解压中，约需 1-3 分钟，请勿关闭窗口 ..." -ForegroundColor Green
    $py = 'C:\Users\x1503\AppData\Local\Programs\Python\Python311\python.exe'
    if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
    if (-not $py) { throw "找不到 Python。请装 7-Zip 后手动解压 $bz2 为 $dat。" }

    $code = 'import bz2,shutil,sys; i=bz2.open(sys.argv[1],"rb"); o=open(sys.argv[2],"wb"); shutil.copyfileobj(i,o,1024*1024); o.close(); i.close()'
    & $py -c $code $bz2 $dat
    if ($LASTEXITCODE -ne 0) { throw "解压失败（Python 退出码 $LASTEXITCODE）。" }
}

$lenGB = [math]::Round((Get-Item $dat).Length / 1GB, 2)
Write-Host "      完成：$dat  ($lenGB GB)" -ForegroundColor Green

if (-not $KeepArchive) {
    Remove-Item $bz2 -Force
    Write-Host "      已删除压缩包（想保留请加 -KeepArchive）" -ForegroundColor DarkGray
}

# ---------- 4. 在 Siril 中启用 ----------
$setCmd = "set core.catalogue_gaia_astro=$dat"
Write-Host ""
Write-Host "================ 接下来在 Siril 里做（二选一） ================" -ForegroundColor Cyan
Write-Host "A) 图形界面：首选项(Preferences) -> Astrometry 页 ->" -ForegroundColor White
Write-Host "   'Gaia astrometric extract:' 选择上面这个文件。" -ForegroundColor White
Write-Host ""
Write-Host "B) 命令行：在 Siril 的 Console 里粘贴执行：" -ForegroundColor White
Write-Host "   $setCmd" -ForegroundColor Yellow
Write-Host ""
Write-Host "完成后：Plate Solving 日志里出现 (local catalogue) 即为生效；" -ForegroundColor White
Write-Host "PCC 对话框 Catalog 选 'Automatic' 或 'Gaia DR3 (local)'。" -ForegroundColor White
Write-Host "==============================================================" -ForegroundColor Cyan

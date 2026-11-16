<#
.SYNOPSIS
    把 C:\Program Files 下的「单个应用目录」安全迁移到其它盘，原路径留一个目录联接(Junction)。
    路径对外不变，程序/注册表/卸载信息都感觉不到变化。

.DESCRIPTION
    用法（管理员 PowerShell）：
        1) 先干跑，看计划           :  .\Move-ProgramFiles-App.ps1 -App "C:\Program Files\PixInsight"
        2) 确认无误再真正执行       :  .\Move-ProgramFiles-App.ps1 -App "C:\Program Files\PixInsight" -Execute
        3) 出问题回滚               :  .\Move-ProgramFiles-App.ps1 -App "C:\Program Files\PixInsight" -Rollback

    - 默认干跑；只有加 -Execute 才会动文件。
    - 只允许 Program Files / Program Files (x86) 的直接子目录；系统组件在拒绝清单里。
    - 执行前必须自己关掉相关程序和 Http 服务（脚本会检测正在运行的进程并中止）。

.NOTES
    绝不要对整个 "C:\Program Files" 或黑名单里的目录执行本脚本。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$App,
    [string]$DestRoot = 'D:\Program Files',
    [switch]$Execute,
    [switch]$Rollback,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
function Say($m, $c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Die($m) { Write-Host "错误: $m" -ForegroundColor Red; exit 1 }

# ---------- 0. 基本校验 ----------
$App = (Resolve-Path -LiteralPath $App).Path.TrimEnd('\')
$parent = Split-Path $App -Parent
if ($parent -notmatch '(?i)^[A-Z]:\\Program Files( \(x86\))?$') {
    Die "只接受 C:\Program Files 或 C:\Program Files (x86) 的直接子目录。当前: $App"
}
$name = Split-Path $App -Leaf
if ($name -eq 'WindowsApps' -or $name -eq 'ModifiableWindowsApps') { Die "WindowsApps 有特殊 ACL，不能迁移。" }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Die "请用「管理员身份」运行 PowerShell。" }

$deny = @(
    'Windows Defender','Windows Defender Advanced Threat Protection','WindowsApps','ModifiableWindowsApps',
    'Windows NT','Windows Mail','Windows Media Player','Windows Photo Viewer','Windows Sidebar',
    'WindowsPowerShell','Common Files','Microsoft','Microsoft Office','Microsoft Office 15','dotnet',
    'MSBuild','Reference Assemblies','Internet Explorer','Uninstall Information','WSL',
    'NVIDIA Corporation','Epic Games','InstallShield Installation Information','edrAgent','Tencent'
)
if ($deny -contains $name) { Die "'$name' 在拒绝清单里（系统组件/驱动/带服务的程序），不要搬。" }

# ---------- 回滚模式 ----------
$bak = "$App.__bak"
if ($Rollback) {
    if (-not (Test-Path -LiteralPath $App)) { Die "原路径不存在: $App" }
    $item = Get-Item -LiteralPath $App -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { Die "原路径不是联接，无需回滚。" }
    $target = @($item.Target)[0]
    Say "当前联接 -> $target" Cyan
    Say "将删除联接并恢复 $bak" Yellow
    if (-not $Yes) {
        $a = Read-Host "确认回滚? 输入 YES"
        if ($a -ne 'YES') { Say '已取消。'; exit 0 }
    }
    & cmd /c rmdir "$App" | Out-Null
    if (-not (Test-Path -LiteralPath $bak)) { Die "备份目录不存在: $bak —— 联接已删，请手动恢复。" }
    Rename-Item -LiteralPath $bak -NewName $name
    Say "已回滚: $App" Green
    exit 0
}

if (-not (Test-Path -LiteralPath $App)) { Die "找不到目录: $App" }
$srcItem = Get-Item -LiteralPath $App -Force
if ($srcItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { Die "$App 已经是联接了，不要再搬。" }

# ---------- 1. 目标与空间 ----------
$dest = Join-Path $DestRoot $name
$drv = (Split-Path $DestRoot -Qualifier).TrimEnd(':')
$vol = Get-Volume -DriveLetter $drv -ErrorAction SilentlyContinue
if (-not $vol) { Die "目标盘不存在: $DestRoot" }
if ($vol.FileSystem -ne 'NTFS') { Die "目标盘必须是 NTFS，当前: $($vol.FileSystem)" }

Say "`n正在统计源目录大小（大目录需要一会儿）..." Cyan
$size = (Get-ChildItem -LiteralPath $App -Recurse -File -Force -ErrorAction SilentlyContinue |
         Measure-Object -Property Length -Sum).Sum
$sizeGB = [math]::Round($size / 1GB, 2)
$freeGB = [math]::Round($vol.SizeRemaining / 1GB, 1)
Say ("源: {0}  ({1} GB)" -f $App, $sizeGB)
Say ("目标: {0}" -f $dest)
Say ("目标盘剩余: {0} GB" -f $freeGB)
if ($freeGB -lt ($sizeGB * 1.05 + 1)) { Die "目标盘空间不足。" }
if (Test-Path -LiteralPath $dest) { Die "目标已存在，请先处理: $dest" }

# ---------- 2. 进程占用检测 ----------
$procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and $_.Path.StartsWith($App, 'OrdinalIgnoreCase') } catch { $false }
}
if ($procs) {
    Say "以下进程仍在运行，先退出它们再执行:" Yellow
    $procs | Select-Object Id, ProcessName, Path | Format-Table -AutoSize | Out-String | Write-Host
    if ($Execute) { Die "有进程占用，已中止。" }
}

# ---------- 3. 计划 ----------
Say "`n================ 行动计划 ================" Cyan
Say " 1. robocopy `"$App`" `"$dest`" /E /COPYALL /DCOPY:DAT /XJ"
Say " 2. 校验文件数与大小"
Say " 3. 原目录改名 -> $bak"
Say " 4. mklink /J `"$App`" `"$dest`""
Say " 5. 校验联接目标"
Say " 6. 保留 $bak 观察 1~2 周后再删"
Say "=========================================`n" Cyan

if (-not $Execute) {
    Say "这是【干跑】，没有改动任何文件。确认无误后加 -Execute 再跑一次。" Green
    exit 0
}
if (-not $Yes) {
    $a = Read-Host "确认执行? 输入 YES"
    if ($a -ne 'YES') { Say '已取消。'; exit 0 }
}

# ---------- 4. 复制 ----------
New-Item -ItemType Directory -Path $DestRoot -Force | Out-Null
Say "`n[1/5] 复制中..." Cyan
& robocopy "$App" "$dest" /E /COPYALL /DCOPY:DAT /XJ /R:1 /W:1 /NP /NFL /NDL /NJH
$rc = $LASTEXITCODE
Say "robocopy 退出码: $rc"
if ($rc -ge 8) { Die "复制失败（退出码 $rc），源目录未改动。" }

# ---------- 5. 校验 ----------
Say "`n[2/5] 校验..." Cyan
$srcCount = (Get-ChildItem -LiteralPath $App -Recurse -File -Force -ErrorAction SilentlyContinue).Count
$dstCount = (Get-ChildItem -LiteralPath $dest -Recurse -File -Force -ErrorAction SilentlyContinue).Count
$dstSize = (Get-ChildItem -LiteralPath $dest -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
Say ("源文件数 {0} / 目标文件数 {1}，源 {2} GB / 目标 {3} GB" -f $srcCount, $dstCount, $sizeGB, [math]::Round($dstSize / 1GB, 2))
if ($srcCount -ne $dstCount -or [math]::Abs($size - $dstSize) -gt 1MB) {
    Die "文件数或大小不一致，已中止（源目录未改动，请检查目标目录后重跑）。"
}

# ---------- 6. 换联接 ----------
Say "`n[3/5] 原目录改名备份..." Cyan
Rename-Item -LiteralPath $App -NewName (Split-Path $bak -Leaf)
Say "`n[4/5] 创建目录联接..." Cyan
& cmd /c mklink /J "$App" "$dest" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say "创建联接失败，正在恢复原目录..." Yellow
    Rename-Item -LiteralPath $bak -NewName $name
    Die "mklink 失败，已回滚。"
}

# ---------- 7. 终检 ----------
Say "`n[5/5] 终检..." Cyan
$now = Get-Item -LiteralPath $App -Force
$tgt = @($now.Target)[0]
Say "联接: $App -> $tgt"
if (-not ($now.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $tgt.TrimEnd('\') -ne $dest.TrimEnd('\')) {
    Die "联接校验失败，请手动检查。备份仍在: $bak"
}

Say "`n完成。接下来请：" Green
Say "  - 启动该程序，做一遍日常操作；能正常更新/卸载最好也试一下"
Say "  - 观察 1~2 周后再删除 $bak（注意：删之前先确认程序一切正常）"
Say "  - 如果某个程序的自动更新把联接覆盖成了真目录（C 盘又变小了），重新跑一次本脚本即可"
Say "  - 不要把 junction 当普通目录去「剪切」，也不要在它上面跑 robocopy /MIR 或清理工具" Yellow

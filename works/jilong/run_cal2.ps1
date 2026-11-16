# Launcher for calibration: start all mu runs as direct children of THIS process.
# Tool-spawned child processes die when the tool call ends, so the parent
# (this script, running inside a background job) must stay alive.
$base = 'F:\DeepSeek工作区\jilong\mf_cal'
$names = @('mu_080','mu_050','mu_030','mu_020')

$procs = @()
foreach ($n in $names) {
    $d = Join-Path $base $n
    Remove-Item "$d\output*.plt", "$d\stdout.log", "$d\cmd.txt", "$d\p.csv" -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath "$d\massflow.exe" -WorkingDirectory $d -NoNewWindow -PassThru `
         -RedirectStandardOutput "$d\stdout.log" -RedirectStandardError "$d\stderr.log"
    Write-Output ("launched {0}  PID={1}  {2}" -f $n, $p.Id, (Get-Date -Format 'HH:mm:ss'))
    $procs += $p
}

# Keep this parent alive until every child exits
foreach ($p in $procs) { $p.WaitForExit() }
Write-Output ("ALL DONE  {0}" -f (Get-Date -Format 'HH:mm:ss'))

# 持续把 mf_hi 的进度写入 status.json，供 progress.html 读取
$dir = 'F:\DeepSeek工作区\jilong'
$log = Join-Path $dir 'mf_hi\stdout.log'
$json = Join-Path $dir 'status.json'
$t0 = $null
$p0 = $null
while ($true) {
    if (Test-Path $log) {
        $lines = Get-Content $log -ErrorAction SilentlyContinue
        $pct = $null; $sim = $null
        for ($i = $lines.Count - 1; $i -ge 0; $i--) {
            if ($lines[$i] -match '([0-9]+\.[0-9]+)\s*%\s*$') {
                $pct = [double]$Matches[1]
                $sim = [double](($lines[$i].Trim() -split '\s+')[0])
                break
            }
        }
        $done = ($lines | Select-String -Pattern 'Computation is done' -Quiet)
        $outs = Get-ChildItem (Join-Path $dir 'mf_hi') -Filter 'output*.plt' -ErrorAction SilentlyContinue
        $mb = 0.0; $nf = 0
        foreach ($o in $outs) { $mb += $o.Length / 1MB; $nf++ }
        $eta = $null
        if ($pct -ne $null -and $pct -gt 0.5 -and $pct -lt 99.9) {
            if ($t0 -eq $null) { $t0 = Get-Date; $p0 = $pct }
            else {
                $el = ((Get-Date) - $t0).TotalSeconds
                $g = $pct - $p0
                if ($g -gt 0.5 -and $el -gt 20) { $eta = [math]::Round($el / $g * (100 - $pct), 0) }
            }
        }
        $obj = [ordered]@{
            percent   = if ($pct -ne $null) { [math]::Round($pct, 2) } else { 0 }
            simTime   = if ($sim -ne $null) { [math]::Round($sim, 1) } else { 0 }
            totalTime = 1200
            frames    = $nf
            outMB     = [math]::Round($mb, 1)
            etaSec    = $eta
            run       = if ($done) { '高精度算例 (20m x 140m)' } else { '高精度算例 (20m x 140m)' }
            updated   = (Get-Date -Format 'HH:mm:ss')
        }
        $obj | ConvertTo-Json -Compress | Out-File -FilePath $json -Encoding utf8
    }
    Start-Sleep -Seconds 5
}

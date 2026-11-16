# 以"新窗口 + 脱离父进程"方式启动 MassFlow 模拟
$bat = 'F:\DeepSeek工作区\jilong\mf_run\run_massflow.bat'
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', ('start "" "' + $bat + '"') -WindowStyle Hidden

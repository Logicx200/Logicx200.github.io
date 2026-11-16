@echo off
rem ---------------------------------------------------------------------------
rem Restart the packaged DeepSeek Harness desktop application, then verify the
rem usage-dashboard plugin end to end.
rem
rem Needed after a change to a plugin's HOST half: the loader recomposes when the
rem ordered bundle list changes, but Node caches an imported module by resolved
rem URL, so edited host source keeps running until the host process is replaced.
rem
rem ASCII only on purpose: cmd interprets batch content in the console code page,
rem so a non-ASCII literal here would be mangled. The plugin directory comes from
rem %~dp0, which cmd expands in Unicode and passes through CreateProcessW.
rem ---------------------------------------------------------------------------
setlocal
set "APP=D:\DeepSeek Harness\DeepSeek Harness.exe"
set "NODE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
set "HERE=%~dp0"
set "PORT=19387"
set "LOG=%HERE%live-report.txt"

echo === DeepSeek Harness restart ===
echo app  %APP%
echo node %NODE%
echo port %PORT%
echo.

if not exist "%APP%" (
  echo FAIL: application not found at %APP%
  pause
  exit /b 1
)
if not exist "%NODE%" (
  echo FAIL: node not found at %NODE%
  pause
  exit /b 1
)

echo [1/4] stopping every "DeepSeek Harness.exe" process ...
taskkill /IM "DeepSeek Harness.exe" /F >nul 2>&1
powershell -NoProfile -Command "Start-Sleep -Seconds 3" >nul

echo [2/4] starting the application ...
start "" "%APP%"

echo [3/4] waiting for the GUI port %PORT% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(120); while ((Get-Date) -lt $deadline) { if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 (
  echo FAIL: the GUI did not come up within 120 seconds.
  echo Start it from the Start Menu, then run the verification below.
  pause
  exit /b 1
)
echo       ready

echo [4/4] verifying the plugin end to end ...
"%NODE%" "%HERE%scripts\verify-live.mjs" --url http://127.0.0.1:%PORT%/ --log "%LOG%"

echo.
echo Report written to %LOG%
echo Expect: all live checks passed, source.artifacts == 11, non-zero "today".
echo.
pause

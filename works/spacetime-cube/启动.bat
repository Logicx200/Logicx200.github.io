@echo off
setlocal
cd /d "%~dp0"

rem ===================================================================
rem  Space-Time Cube launcher
rem
rem  This file is intentionally English-only ASCII with CRLF line endings.
rem  cmd.exe parses .bat files byte by byte using the system ANSI code page,
rem  so non-ASCII text (Chinese, etc.) gets decoded wrongly and breaks the
rem  line structure - cmd then tries to run fragments of text as commands.
rem  Keep it ASCII.
rem
rem  The local server is started in a separate MINIMIZED console window
rem  titled "spacetime-cube server", so that you can see and close it.
rem ===================================================================

set "PORT=8730"
set "URL=http://127.0.0.1:%PORT%/"

where node >nul 2>nul
if not errorlevel 1 goto use_node

where python >nul 2>nul
if not errorlevel 1 goto use_python

where py >nul 2>nul
if not errorlevel 1 goto use_py

goto no_runtime

:use_node
echo Starting local server (Node)...
start "spacetime-cube server" /min cmd /c node "%~dp0server.js" %PORT%
goto wait

:use_python
echo Starting local server (Python)...
start "spacetime-cube server" /min cmd /c python -m http.server %PORT% --bind 127.0.0.1 --directory "%~dp0."
goto wait

:use_py
echo Starting local server (py)...
start "spacetime-cube server" /min cmd /c py -m http.server %PORT% --bind 127.0.0.1 --directory "%~dp0."
goto wait

:wait
echo Waiting for http://127.0.0.1:%PORT%/ ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "for($i=0;$i -lt 40;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',%PORT%);$c.Close();exit 0}catch{Start-Sleep -Milliseconds 250}};exit 1"
if errorlevel 1 goto failed

start "" "%URL%"
echo.
echo   Space-Time Cube is running at %URL%
echo.
echo   A minimized window titled "spacetime-cube server" is serving the files.
echo   To stop the server later, close that window (or: taskkill /f /im node.exe).
echo   You can close THIS window now.
echo.
pause
exit /b 0

:no_runtime
echo.
echo   Neither Node.js nor Python was found on this machine.
echo.
echo   Options:
echo     1. Install Node.js from https://nodejs.org/  (then run this again)
echo     2. In VS Code, right-click index.html and choose "Open with Live Server"
echo.
pause
exit /b 1

:failed
echo.
echo   The server did not come up on port %PORT%.
echo   The port may already be in use.
echo.
echo   Try another port:   node server.js 8731
echo   then open:          http://127.0.0.1:8731/
echo.
pause
exit /b 1

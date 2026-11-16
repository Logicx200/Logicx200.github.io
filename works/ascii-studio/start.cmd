@echo off
setlocal
cd /d "%~dp0"
title ASCII Studio

if not exist "server.js" goto missing
where node >nul 2>nul
if errorlevel 1 goto nonode

node server.js
if errorlevel 1 pause
goto end

:missing
echo.
echo   server.js was not found next to start.cmd.
echo.
pause
goto end

:nonode
echo.
echo   Node.js was not found.
echo   Install Node.js 18 or newer: https://nodejs.org/
echo.
pause

:end
endlocal

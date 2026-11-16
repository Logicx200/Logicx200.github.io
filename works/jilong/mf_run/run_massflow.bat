@echo off
title MassFlow-Jilong
cd /d "%~dp0"
echo ================================================================
echo   MassFlow 2.9   Jilong ice-rock avalanche  (2026-08-26)
echo ----------------------------------------------------------------
echo   Domain : 770 x 1166 cells @ 30 m   (UTM 45N)
echo   Source : 85.2953E 28.4997N   5288 m
echo   Outlet : 85.3775E 28.2786N   1783 m
echo   Volume : 70.0e6 m3     Total : 400 s
echo ================================================================
echo.
echo   Progress is shown below AND streamed to stdout.log
echo   (the on-page progress bar reads that file).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\massflow.exe' 2>&1 | Tee-Object -FilePath 'stdout.log'"
echo.
echo ================================================================
echo   MassFlow finished.  EXIT CODE = %ERRORLEVEL%
echo ================================================================
echo.
pause

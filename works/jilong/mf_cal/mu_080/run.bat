@echo off
cd /d "%~dp0"
massflow.exe > stdout.log 2> stderr.log
echo DONE %~n0 exit=%ERRORLEVEL% >> _status.txt
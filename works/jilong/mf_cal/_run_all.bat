@echo off
cd /d "%~dp0"
for %%D in (mu_080 mu_050 mu_030 mu_020) do (
  echo === START %%D %DATE% %TIME% ===
  call "%%D\run.bat"
  echo === END   %%D %DATE% %TIME% ===
)
echo ALL_CALIBRATION_DONE
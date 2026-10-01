@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
  python -m gui.launcher %*
  goto result
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m gui.launcher %*
  goto result
)

echo Python 3.10 or later was not found in PATH.
pause
exit /b 1

:result
if errorlevel 1 (
  echo.
  echo GUI failed to start. Review the error above and try again.
  pause
)

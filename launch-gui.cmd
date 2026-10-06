@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv-gui\Scripts\pythonw.exe" (
  start "" "%~dp0.venv-gui\Scripts\pythonw.exe" "%~dp0launch-gui.pyw" %*
  exit /b 0
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0launch-gui.pyw" %*
  exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0launch-gui.pyw" %*
  exit /b 0
)

echo A Python 3.10+ windowed launcher (pythonw or pyw) was not found in PATH.
pause
exit /b 1

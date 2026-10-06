@echo off
setlocal
if exist "%~dp0.venv-gui\Scripts\python.exe" goto localpython
python "%~dp0launch-cli.py" %*
exit /b %errorlevel%
:localpython
"%~dp0.venv-gui\Scripts\python.exe" "%~dp0launch-cli.py" %*
exit /b %errorlevel%

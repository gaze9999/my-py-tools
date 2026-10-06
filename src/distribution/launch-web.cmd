@echo off
setlocal
call "%~dp0launch-cli.cmd" --web %*
exit /b %errorlevel%

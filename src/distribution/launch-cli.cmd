@echo off
setlocal
"%~dp0launch-cli.exe" %*
exit /b %errorlevel%

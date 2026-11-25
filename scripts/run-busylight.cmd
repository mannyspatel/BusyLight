@echo off
setlocal
cd /d "%~dp0.."
if not defined PYTHONW set PYTHONW=pythonw
"%PYTHONW%" busylight.py
exit /b %ERRORLEVEL%
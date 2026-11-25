@echo off
setlocal
cd /d "%~dp0"
start "BusyLight Setup" powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-dependencies.ps1"
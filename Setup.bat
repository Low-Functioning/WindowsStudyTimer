@echo off
title Study Timer - Setup
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
if errorlevel 1 (
    echo.
    echo Setup did not finish. See the message above.
    pause
    exit /b 1
)
exit /b 0

@echo off
rem ------------------------------------------------------------
rem  ONT channel switch - launcher
rem  Double-click to get the interactive menu.
rem  All Chinese UI text comes from tools\ont.py (UTF-8 safe).
rem  This file is pure ASCII on purpose.
rem ------------------------------------------------------------
chcp 65001 >nul 2>&1
call "%~dp0tools\ont.bat" %*
endlocal & exit /b %ERRORLEVEL%
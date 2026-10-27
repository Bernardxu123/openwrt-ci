@echo off
rem ============================================================
rem  ONT access channel switch  (FiberHome HG5585F, CU / Unicom)
rem
rem  Double-click this file  -> interactive menu, pick what you want.
rem  Or pass an action:
rem      ont.bat status         show status only
rem      ont.bat on             enable  (auto-removed after 1800s)
rem      ont.bat on --ttl 7200  enable  (2 hours)
rem      ont.bat on --ttl 0     enable  (keep on until manually closed)
rem      ont.bat off            disable now
rem      ont.bat toggle         toggle on/off
rem
rem  NOTE: this file is intentionally pure ASCII. The Chinese UI text
rem        is printed by ont.py, which handles UTF-8 itself. Keeping CJK
rem        out of a .bat avoids cmd.exe mis-parsing it under codepage 936.
rem ============================================================

chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"

set "PY="
for %%C in (python.exe python3.exe py.exe) do (
    if not defined PY (
        for /f "delims=" %%P in ('where %%C 2^>nul') do (
            if not defined PY set "PY=%%P"
        )
    )
)

if not defined PY goto :nopython

if "%~1"=="" (
    "%PY%" "%~dp0ont.py"
) else (
    "%PY%" "%~dp0ont.py" %*
)
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo   [exit code %RC%]
pause
endlocal & exit /b %RC%

:nopython
echo.
echo   [ERROR] Python not found.
echo.
echo   Install Python 3 and make sure python or py is on PATH,
echo   or drop a python.exe next to this script and retry.
echo.
pause
endlocal & exit /b 9009
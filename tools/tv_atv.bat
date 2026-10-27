@echo off
REM Switch TV foreground to ATV Launcher (kills JuHaoKan launcher process only)
REM NOTE: package state stays ENABLED, so reboots are ALWAYS safe.
cd /d %~dp0
set ADB=platform-tools\adb.exe
%ADB% connect 192.168.31.115:5555
%ADB% -s 192.168.31.115:5555 shell "am force-stop com.jamdeo.tv.vod; sleep 2; dumpsys window | grep mCurrentFocus | head -1"
pause

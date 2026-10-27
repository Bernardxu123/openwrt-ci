@echo off
REM Bring JuHaoKan launcher back to foreground
cd /d %~dp0
set ADB=platform-tools\adb.exe
%ADB% connect 192.168.31.115:5555
%ADB% -s 192.168.31.115:5555 shell "am start -n com.jamdeo.tv.vod/com.ju.main.launcher.LauncherActivity"
pause

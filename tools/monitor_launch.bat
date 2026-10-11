@echo off
rem ZCode 会话监测台（新窗口 + 置顶）——输出留日志便于排查
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0monitor_launch.ps1" > "%TEMP%\monitor_launch.log" 2>&1

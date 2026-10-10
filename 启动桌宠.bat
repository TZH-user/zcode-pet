@echo off
rem ZCode 桌宠启动器（dev 源码运行，无控制台窗口）
start "" "%~dp0pet\node_modules\electron\dist\electron.exe" "%~dp0pet"

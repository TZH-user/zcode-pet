# 启动 ZCode 会话监测台（新窗口 + 置顶）
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$arg = "-NoProfile -ExecutionPolicy Bypass -NoExit -Command `"python '$dir\monitor_console.py'`""
$p = Start-Process powershell -ArgumentList $arg -PassThru
Start-Sleep -Milliseconds 1500
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Win32Top {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
}
"@
try {
    $h = (Get-Process -Id $p.Id).MainWindowHandle
    [Win32Top]::SetWindowPos($h, [IntPtr](-1), 80, 80, 0, 0, 0x0001 -bor 0x0040) | Out-Null
} catch { }

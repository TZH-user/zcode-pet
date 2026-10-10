# ZCode hook 兜底拉起桌宠（SessionStart/UserPromptSubmit 触发，async 不阻塞）
# 注意：本文件必须保存为 UTF-8 with BOM（PowerShell 5.1 中文注释兼容）
$ErrorActionPreference = 'SilentlyContinue'
$bat = 'F:\Zcode\桌宠\启动桌宠.bat'
$running = Get-CimInstance Win32_Process -Filter "Name='electron.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*\pet*' }
if (-not $running -and (Test-Path $bat)) {
    Start-Process cmd.exe -ArgumentList '/c', $bat -WindowStyle Hidden
}
exit 0

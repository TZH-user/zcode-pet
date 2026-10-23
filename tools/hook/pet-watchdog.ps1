# ZCode 桌宠启动看门狗（登录自启 → ZCode 出现即拉起桌宠）
#
# 为什么不用 ZCode 的 SessionStart hook：
#   实测 hooks 已在 ~/.zcode/cli/config.json 正确注册（hooks.events.SessionStart /
#   UserPromptSubmit，格式无误），且写入时间比 ZCode 最后一次启动早 43 小时，
#   但 ZCode 启动日志里 "pet-hook" 从未出现过一次 —— ZCode 桌面端根本没有派发
#   这些 hook。所以"随 ZCode 启动"这一层一直是死的，只能由外部看门狗补上。
#
# 为什么不用 Get-Process -Name electron 判断"桌宠在跑"：
#   本机同时跑着 ZCode / WorkBuddy / opencode 桌面版 / Tabbit 等多个 Electron
#   应用，只看进程名会永远误判为"在跑"，桌宠就再也起不来。改为读桌宠自己写的
#   pet.lock（里面是它的 PID）。
#
# 本文件必须存为 UTF-8 with BOM：含中文注释，PS 5.1 按 GBK 读会直接语法错误
# （本项目已踩两次，见记忆条目 5/20）。

$ErrorActionPreference = 'SilentlyContinue'
$BAT  = 'F:\Zcode\桌宠\启动桌宠.bat'
$UPD  = Join-Path $env:APPDATA 'zcode-pet'
$LOCK = Join-Path $UPD 'pet.lock'
$HOLD = Join-Path $UPD 'no-autostart'   # 存在 = 用户主动退出过，暂不自动拉起
$LOG  = Join-Path $env:TEMP 'zcode-pet-watchdog.log'

function Say($m) {
    Add-Content -LiteralPath $LOG -Value ("[" + (Get-Date -Format 'HH:mm:ss') + "] $m") -Encoding UTF8
}

Say "看门狗启动（PID $PID）"

function Test-PetAlive {
    # 返回 $true 表示桌宠确实在跑（读它自己写的 pet.lock 里的 PID）
    if (-not (Test-Path -LiteralPath $LOCK)) { return $false }
    $raw = Get-Content -LiteralPath $LOCK -Raw
    if ($raw -notmatch '^\s*(\d+)\s*$') { return $false }
    return [bool](Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue)
}

$lastLaunch = [datetime]::MinValue

while ($true) {
    $zcode = Get-Process -Name ZCode -ErrorAction SilentlyContinue
    if ($zcode -and -not (Test-Path -LiteralPath $HOLD)) {
        if (-not (Test-PetAlive)) {
            # 冷却：一次拉起失败后不要立刻重试，避免桌宠起不来时空转刷屏
            if (((Get-Date) - $lastLaunch).TotalSeconds -lt 30) {
                Start-Sleep -Seconds 4
                continue
            }
            $lastLaunch = Get-Date
            Say "ZCode 在跑且桌宠未运行 → 拉起"
            Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $BAT -WindowStyle Hidden
            # 轮询等 lock 出现，不要盲等固定秒数：electron 冷启动 + 168 帧解码
            # 可能超过 10s，盲等会导致重复拉起（单实例锁会让第二个秒退，但白费资源）
            $ready = $false
            for ($i = 0; $i -lt 60; $i++) {
                Start-Sleep -Milliseconds 500
                if (Test-PetAlive) { $ready = $true; break }
            }
            Say $(if ($ready) { "桌宠已就绪（用时约 $([int]((Get-Date)-$lastLaunch).TotalSeconds)s）" }
                    else { "拉起后 30s 内未就绪，稍后重试" })
        }
    }
    Start-Sleep -Seconds 4
}
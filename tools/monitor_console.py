# -*- coding: utf-8 -*-
"""ZCode 会话监测台（控制台实时面板，供人工验收）。

用法: python tools/monitor_console.py [--once] [--interval 2]
置顶窗口启动: tools/monitor_launch.bat
"""
import argparse
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from zcode_state import STATE_LABEL, StateSource   # noqa: E402

C = {"r": "\033[91m", "g": "\033[92m", "y": "\033[93m", "c": "\033[96m",
     "d": "\033[90m", "b": "\033[94m", "w": "\033[97m", "0": "\033[0m"}
STATE_COLOR = {"working": "c", "idle": "g", "notification": "y",
               "error": "r", "waiting": "y", "sleeping": "d"}


def enable_vt():
    if sys.platform != "win32":
        return
    k = ctypes.windll.kernel32
    h = k.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if k.GetConsoleMode(h, ctypes.byref(mode)):
        k.SetConsoleMode(h, mode.value | 0x0004)


def fmt_time(ms):
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S") if ms else "--"


def render(m: dict) -> str:
    L = []
    sc = C[STATE_COLOR.get(m["state"], "w")]
    dot = f'{C["g"]}●{C["0"]}' if m["process"] else f'{C["r"]}○{C["0"]}'
    L.append("═" * 30 + " ZCode 桌宠 · 会话监测台 " + "═" * 14)
    L.append(f' 采样时间 {m["ts"]}   ZCode 进程 {dot}   每 2 秒刷新，Ctrl+C 退出')
    L.append(f' 桌宠状态(仲裁): {sc}{m["state"].upper():<12} {STATE_LABEL[m["state"]]}{C["0"]}')
    L.append("─" * 66)
    work = f'{C["c"]}{m["running_sessions"]}{C["0"]}' if m["running_sessions"] else "0"
    act = f'{C["c"]}{m["active_sessions"]}{C["0"]}' if m["active_sessions"] else "0"
    unread = f'{C["y"]}{m["unread"]}{C["0"]}' if m["unread"] else "0"
    err = f'{C["r"]}{m["errors"]}{C["0"]}'
    new = f'  (监测期间新增 {C["r"]}{m["error_new"]}{C["0"]})' if m["error_new"] else ""
    L.append(f' 运行中会话: {work}   正在执行工具: {m["running_tools"]}   90s内活跃: {act}')
    L.append(f' 未读会话:   {unread}        错误任务(累计): {err}{new}')
    L.append("─" * 30 + " 会话列表(最近) " + "─" * 19)
    if not m["sessions"]:
        L.append(f' {C["d"]}(无交互会话记录){C["0"]}')
    for sid, title, tu in m["sessions"]:
        age = int(m.get("_now_ms", 0) - tu) // 1000 if tu else -1
        mark = f'{C["c"]}▶{C["0"]}' if 0 <= age <= 90 else " "
        L.append(f' {mark} {sid}  {title:<36}{C["d"]}{fmt_time(tu)}{C["0"]}')
    if m["error_tasks"]:
        L.append("─" * 28 + " 最近错误任务 " + "─" * 24)
        for tid, title, upd in m["error_tasks"]:
            L.append(f'   {tid}  {title:<34}{C["d"]}{fmt_time(upd)}{C["0"]}')
    L.append("─" * 66)
    L.append(f' {C["d"]}working=工具执行中或90s内有会话活动 | waiting 需第二阶段接 hooks | '
             f'状态口径见 docs/01{C["0"]}')
    if m["data_error"]:
        L.append(f' {C["r"]}数据源异常: {m["data_error"]}{C["0"]}')
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只采样一帧退出（自检用）")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    enable_vt()
    src = StateSource()
    if args.once:
        m = src.poll()
        m["_now_ms"] = int(__import__("time").time() * 1000)
        print(render(m))
        return
    print("\033[2J", end="")
    while True:
        m = src.poll()
        m["_now_ms"] = int(__import__("time").time() * 1000)
        frame = render(m)
        print("\033[H" + frame + "\n", end="", flush=True)
        import time as _t
        _t.sleep(args.interval)


if __name__ == "__main__":
    main()

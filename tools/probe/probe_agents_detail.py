# -*- coding: utf-8 -*-
"""Full table/column detail for OpenCode + WorkBuddy so the adapter design is
grounded in what actually exists, not assumptions."""
import os
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

WANT = {
    "OpenCode": os.path.join(HOME, ".local", "share", "opencode", "opencode.db"),
    "WorkBuddy": os.path.join(HOME, ".workbuddy", "workbuddy.db"),
}

for name, db in WANT.items():
    print("=" * 72)
    print(f"### {name}  ({os.path.getsize(db)/1e6:.1f} MB)")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tabs = [r[0] for r in cur.fetchall()]
    print(f"  ALL tables ({len(tabs)}): {tabs}")
    for t in tabs:
        if t not in ("session", "sessions", "tool_usage", "turn_usage", "part",
                     "message", "session_input", "session_entry", "workspace",
                     "session_usage", "model_usage"):
            continue
        cur.execute(f"PRAGMA table_info('{t}')")
        cols = [(r[1], r[2]) for r in cur.fetchall()]
        print(f"  [{t}] {cols}")
    # 关键问题：能不能拿到"正在跑的工具"
    print("  -- 运行中工具的候选信号 --")
    for t in tabs:
        try:
            cur.execute(f"PRAGMA table_info('{t}')")
            cols = [r[1] for r in cur.fetchall()]
        except Exception:
            continue
        hits = [c for c in cols if c.lower() in ("status", "state", "started_at", "completed_at")]
        if hits and t in ("tool_usage", "turn_usage", "sessions", "session", "tool", "tool_call"):
            print(f"    {t}: {hits}")
    # 实测几个候选查询
    cands = []
    if "tool_usage" in tabs:
        cands.append(("tool_usage WHERE status='running'",
                      "SELECT COUNT(*) FROM tool_usage WHERE status='running'"))
    if "turn_usage" in tabs:
        cands.append(("turn_usage WHERE status='running'",
                      "SELECT COUNT(*) FROM turn_usage WHERE status='running'"))
    if "sessions" in tabs:
        cands.append(("sessions status 分布",
                      "SELECT status, COUNT(*) FROM sessions GROUP BY status"))
    if "session" in tabs:
        cands.append(("session 最近活跃(60s)",
                      "SELECT COUNT(*) FROM session WHERE time_updated > 0"))
    for label, sql in cands:
        try:
            rows = con.execute(sql).fetchall()
            print(f"    OK {label} -> {rows[:6]}")
        except Exception as e:
            print(f"    ERR {label} -> {e}")
    con.close()
    print()
# -*- coding: utf-8 -*-
"""Can we build one adapter interface across agents? Probe each store.

For each agent, answer the two questions the pet actually needs:
  Q1 liveness   : is it running?
  Q2 activity   : sessions / tools-running / unread / errors
and report whether the probe is CHEAP and STABLE (schema present) or fragile.
"""
import glob
import os
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

TARGETS = [
    ("ZCode", os.path.join(HOME, ".zcode", "cli", "db", "db.sqlite"),
     os.path.join(HOME, ".zcode", "v2", "tasks-index.sqlite")),
    ("OpenCode", os.path.join(HOME, ".local", "share", "opencode", "opencode.db"), None),
    ("WorkBuddy", os.path.join(HOME, ".workbuddy", "workbuddy.db"), None),
]


def tables(con):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in cur.fetchall()}


def probe(name, db, db2):
    print("=" * 70)
    print(f"### {name}")
    if not os.path.exists(db):
        print(f"  MISSING: {db}")
        return
    size = os.path.getsize(db) / 1e6
    print(f"  db = {db}")
    print(f"  size = {size:.1f} MB")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        t = tables(con)
    except Exception as e:
        print(f"  OPEN FAILED: {e}")
        return
    print(f"  tables({len(t)}) = {sorted(t)[:14]}")

    # Q2: can we count sessions + running tools + recent activity?
    probes = [
        ("sessions", [
            ("session", "SELECT COUNT(*) n FROM session WHERE time_updated > ? AND task_type='interactive'"),
            ("sessions", "SELECT COUNT(*) n FROM session"),
        ]),
        ("tool_usage.status='running'", [
            ("tool_usage", "SELECT COUNT(*) n FROM tool_usage WHERE status='running'"),
            ("tool_usage", "SELECT COUNT(*) n FROM tool_usage"),
        ]),
    ]
    for label, cands in probes:
        for tbl, sql in cands:
            if tbl in t:
                try:
                    n = con.execute(sql, (0,) if "?" in sql else ()).fetchone()[0]
                    print(f"  OK   {label:28s} -> {n}")
                except Exception as e:
                    print(f"  ERR  {label:28s} -> {e}")
                break
        else:
            print(f"  MISS {label:28s} (no candidate table)")

    # unread / errors
    for label, sql in [("unread", "SELECT COUNT(*) n FROM tasks WHERE unread_at IS NOT NULL"),
                       ("errors", "SELECT COUNT(*) n FROM tasks WHERE task_status='error'")]:
        try:
            n = con.execute(sql).fetchone()[0]
            print(f"  OK   {label:28s} -> {n}")
        except Exception:
            print(f"  --   {label:28s} -> 表不存在/列不匹配")
    con.close()

    if db2:
        print(f"  db2 = {db2}")
        if os.path.exists(db2):
            try:
                c2 = sqlite3.connect(f"file:{db2}?mode=ro", uri=True)
                t2 = tables(c2)
                print(f"  db2 tables = {sorted(t2)[:12]}")
                c2.close()
            except Exception as e:
                print(f"  db2 OPEN FAILED: {e}")
        else:
            print("  db2 MISSING")
    print()


for nm, d1, d2 in TARGETS:
    probe(nm, d1, d2)

# WorkBuddy also has per-session jsonl under projects/
pj = os.path.join(HOME, ".workbuddy", "projects")
n = len(glob.glob(os.path.join(pj, "*", "*.jsonl")))
print(f"WorkBuddy projects/*/*.jsonl = {n} files  (备选信号源：文件 mtime 增量)")
# -*- coding: utf-8 -*-
"""ZCode 会话状态源——桌宠监控层参考实现（全部只读，不写任何 ZCode 数据）。

数据源（依据 docs/01-zcode-source-analysis.md 的实测结论）：
  - ~/.zcode/v2/tasks-index.sqlite  tasks 表：未读(unread_at) / 任务终态(task_status)
  - ~/.zcode/cli/db/db.sqlite       tool_usage：实时工具执行(running 行)；
                                    session：会话列表与活跃时间(90s 口径)
  - 进程轮询 tasklist：ZCode.exe 是否运行（hooks 无 SessionEnd，退出只能轮询）

派生状态（优先级自高到低）：
  sleeping（进程不在） > working（工具执行中 / 90s 内有会话活动）
  > notification（有未读） > error（监测期间出现新错误任务） > idle
  waiting（PermissionRequest）需 hooks 才能实时检测，此处留待第二阶段接入。
"""
import sqlite3
import subprocess
import time
from pathlib import Path

HOME = Path.home()
TASKS_DB = HOME / ".zcode" / "v2" / "tasks-index.sqlite"
SESSION_DB = HOME / ".zcode" / "cli" / "db" / "db.sqlite"
ACTIVE_WINDOW_S = 90      # 旧项目 35 分钟零误判验证过的"实时在跑"口径

STATE_LABEL = {
    "working": "奔跑工作中",
    "idle": "悠闲待机",
    "notification": "有未读会话!",
    "error": "出错了!",
    "waiting": "等待确认!",
    "sleeping": "ZCode 已关闭",
}


def _ro(db: Path):
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3)


def zcode_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ZCode.exe"],
                         capture_output=True, creationflags=0x08000000).stdout
    return "ZCode.exe" in out.decode("gbk", errors="ignore")


class StateSource:
    """持续轮询的状态源；error 只在"监测期间新增"时置位，避免历史错误常驻。"""

    def __init__(self):
        self._baseline_errors = None

    def poll(self) -> dict:
        now_ms = int(time.time() * 1000)
        m = {"ts": time.strftime("%H:%M:%S"), "process": zcode_running(),
             "running_tools": 0, "running_sessions": 0, "active_sessions": 0,
             "unread": 0, "errors": 0, "error_new": 0,
             "sessions": [], "error_tasks": [], "data_error": None}
        try:
            con = _ro(SESSION_DB)
            cur = con.cursor()
            m["running_sessions"] = cur.execute(
                "SELECT COUNT(DISTINCT session_id) FROM tool_usage WHERE status='running'").fetchone()[0]
            m["running_tools"] = cur.execute(
                "SELECT COUNT(*) FROM tool_usage WHERE status='running'").fetchone()[0]
            m["active_sessions"] = cur.execute(
                "SELECT COUNT(*) FROM session WHERE time_updated > ? AND task_type='interactive'",
                (now_ms - ACTIVE_WINDOW_S * 1000,)).fetchone()[0]
            for sid, title, tu in cur.execute(
                    "SELECT substr(id,1,12), replace(substr(title,1,34), char(10), ' '), time_updated "
                    "FROM session WHERE task_type='interactive' ORDER BY time_updated DESC LIMIT 6"):
                m["sessions"].append((sid, title, tu))
            con.close()
        except Exception as e:
            m["data_error"] = f"db.sqlite: {e}"
        try:
            con = _ro(TASKS_DB)
            cur = con.cursor()
            m["unread"] = cur.execute(
                "SELECT COUNT(*) FROM tasks WHERE unread_at IS NOT NULL AND deleted=0 "
                "AND archived=0 AND task_id LIKE 'sess_%'").fetchone()[0]
            m["errors"] = cur.execute(
                "SELECT COUNT(*) FROM tasks WHERE task_status='error' AND deleted=0 "
                "AND archived=0 AND task_id LIKE 'sess_%'").fetchone()[0]
            for tid, title, upd in cur.execute(
                    "SELECT substr(task_id,1,16), replace(substr(title,1,34), char(10), ' '), updated_at "
                    "FROM tasks WHERE task_status='error' AND deleted=0 AND archived=0 "
                    "AND task_id LIKE 'sess_%' ORDER BY updated_at DESC LIMIT 3"):
                m["error_tasks"].append((tid, title, upd))
            con.close()
        except Exception as e:
            m["data_error"] = f"{m['data_error'] or ''} | tasks-index: {e}"

        if self._baseline_errors is None:
            self._baseline_errors = m["errors"]
        m["error_new"] = max(0, m["errors"] - self._baseline_errors)
        m["state"] = self.derive(m)
        return m

    @staticmethod
    def derive(m: dict) -> str:
        if not m["process"]:
            return "sleeping"
        if m["running_tools"] or m["running_sessions"] or m["active_sessions"]:
            return "working"
        if m["unread"]:
            return "notification"
        if m["error_new"]:
            return "error"
        return "idle"


if __name__ == "__main__":
    import json
    print(json.dumps(StateSource().poll(), ensure_ascii=False, indent=2, default=str))

// ZCode 会话状态源（Node 版，与 tools/zcode_state.py 同口径）
// 数据源全部只读；口径依据 docs/01-zcode-source-analysis.md
"use strict";
const { DatabaseSync } = require("node:sqlite");
const { spawn } = require("child_process");
const os = require("os");
const path = require("path");

const TASKS_DB = path.join(os.homedir(), ".zcode", "v2", "tasks-index.sqlite");
const SESSION_DB = path.join(os.homedir(), ".zcode", "cli", "db", "db.sqlite");
const ACTIVE_WINDOW_S = 90; // 旧项目 35 分钟零误判验证的"实时在跑"口径

const STATE_LABEL = {
  working: "全力奔跑中",
  walk: "踱步思考中",
  idle: "悠闲待机",
  notification: "有未读会话!",
  error: "出错了!",
  waiting: "等待确认!",
  sleeping: "ZCode 已关闭",
};

function zcodeRunning() {
  return new Promise((resolve) => {
    const p = spawn("tasklist", ["/FI", "IMAGENAME eq ZCode.exe"], {
      windowsHide: true,
    });
    let out = "";
    p.stdout.on("data", (d) => (out += d.toString("binary")));
    p.on("error", () => resolve(false));
    p.on("close", () => resolve(out.includes("ZCode.exe")));
  });
}

function ro(db) {
  return new DatabaseSync(db, { readOnly: true });
}

class StateSource {
  constructor() {
    this._baselineErrors = null;
  }

  async poll() {
    const nowMs = Date.now();
    const m = {
      ts: new Date().toTimeString().slice(0, 8),
      process: await zcodeRunning(),
      runningTools: 0, runningSessions: 0, activeSessions: 0,
      unread: 0, errors: 0, errorNew: 0,
      sessions: [], errorTasks: [], dataError: null,
    };
    try {
      const db = ro(SESSION_DB);
      m.runningSessions = db
        .prepare("SELECT COUNT(DISTINCT session_id) n FROM tool_usage WHERE status='running'")
        .get().n;
      m.runningTools = db
        .prepare("SELECT COUNT(*) n FROM tool_usage WHERE status='running'")
        .get().n;
      m.activeSessions = db
        .prepare("SELECT COUNT(*) n FROM session WHERE time_updated > ? AND task_type='interactive'")
        .get(nowMs - ACTIVE_WINDOW_S * 1000).n;
      m.sessions = db
        .prepare("SELECT substr(id,1,12) sid, replace(substr(title,1,34), char(10), ' ') title, time_updated tu FROM session WHERE task_type='interactive' ORDER BY time_updated DESC LIMIT 6")
        .all();
      db.close();
    } catch (e) {
      m.dataError = "db.sqlite: " + e.message;
    }
    try {
      const db = ro(TASKS_DB);
      m.unread = db
        .prepare("SELECT COUNT(*) n FROM tasks WHERE unread_at IS NOT NULL AND deleted=0 AND archived=0 AND task_id LIKE 'sess_%'")
        .get().n;
      m.errors = db
        .prepare("SELECT COUNT(*) n FROM tasks WHERE task_status='error' AND deleted=0 AND archived=0 AND task_id LIKE 'sess_%'")
        .get().n;
      m.errorTasks = db
        .prepare("SELECT substr(task_id,1,16) tid, replace(substr(title,1,34), char(10), ' ') title, updated_at upd FROM tasks WHERE task_status='error' AND deleted=0 AND archived=0 AND task_id LIKE 'sess_%' ORDER BY updated_at DESC LIMIT 3")
        .all();
      db.close();
    } catch (e) {
      m.dataError = (m.dataError ? m.dataError + " | " : "") + "tasks-index: " + e.message;
    }
    if (this._baselineErrors === null) this._baselineErrors = m.errors;
    m.errorNew = Math.max(0, m.errors - this._baselineErrors);
    m.state = this.derive(m);
    return m;
  }

  derive(m) {
    if (!m.process) return "sleeping";
    // 分档（对齐旧项目口径）：1 会话=踱步，2+ 会话=全力跑
    const active = Math.max(m.activeSessions, m.runningSessions);
    if (active >= 2) return "working";
    if (active === 1) return "walk";
    if (m.unread) return "notification";
    if (m.errorNew) return "error";
    return "idle";
  }
}

module.exports = { StateSource, STATE_LABEL, ACTIVE_WINDOW_S, zcodeRunning };

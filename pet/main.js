// ZCode 桌宠 主进程：透明置顶窗口 + 会话状态轮询 + 帧素材 IPC
// 经验规避：禁 GPU 加速防透明立绘丢失；异常落盘不弹窗；单实例锁
"use strict";
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");
const { StateSource, STATE_LABEL } = require("./zcode_state");

const APP_VERSION = require("./package.json").version;
const ROOT = path.resolve(__dirname, "..");
const SPR = path.join(ROOT, "assets", "sprites", "luotianyi");
const manifest = JSON.parse(fs.readFileSync(path.join(SPR, "manifest.json"), "utf8"));

function logLine(msg) {
  try {
    fs.appendFileSync(path.join(process.env.TEMP || ".", "zcode-pet.log"),
      `[${new Date().toISOString()}] ${msg}\n`);
  } catch (_) { }
}

process.on("uncaughtException", (e) => logLine(e.stack || String(e)));

app.disableHardwareAcceleration();
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  bootstrap();
}

let win = null;
let tray = null;
let quitting = false;
let currentState = "idle";
let celebrateTimer = null;
const src = new StateSource();

function bootstrap() {
  app.whenReady().then(() => {
    createWindow();
    createTray();
    setInterval(pollLoop, 2000);
    setTimeout(pollLoop, 300);
  });
  app.on("second-instance", () => {
    if (win && !win.isDestroyed()) { win.show(); ensureOnScreen(); }
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => { quitting = true; });
}

function createWindow() {
  const wa = screen.getPrimaryDisplay().workArea;
  win = new BrowserWindow({
    width: 380,
    height: 430,
    x: wa.x + wa.width - 400,
    y: wa.y + wa.height - 460,
    transparent: true,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setAlwaysOnTop(true, "screen-saver");
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.webContents.on("console-message", (_e, level, message, line, sourceId) => {
    if (level >= 2) logLine(`renderer[${level}] ${message} (${path.basename(String(sourceId))}:${line})`);
  });
  win.webContents.on("render-process-gone", (_e, details) => logLine("render-gone: " + JSON.stringify(details)));
  win.webContents.on("did-fail-load", (_e, code, desc) => logLine(`did-fail-load ${code} ${desc}`));
  win.on("moved", ensureOnScreen);
}

function ensureOnScreen() {
  if (!win || win.isDestroyed()) return;
  const wa = screen.getPrimaryDisplay().workArea;
  const [x, y] = win.getPosition();
  const nx = Math.min(Math.max(x, wa.x - 40), wa.x + wa.width - 80);
  const ny = Math.min(Math.max(y, wa.y - 10), wa.y + wa.height - 80);
  if (nx !== x || ny !== y) win.setPosition(nx, ny);
}

function createTray() {
  const iconPath = path.join(__dirname, "build", "icon.ico");
  tray = new Tray(iconPath);
  tray.setToolTip("ZCode 桌宠 v" + APP_VERSION);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "ZCode 桌宠 v" + APP_VERSION, enabled: false },
    { type: "separator" },
    { label: "回到右下角", click: () => {
        const wa = screen.getPrimaryDisplay().workArea;
        if (win && !win.isDestroyed()) win.setPosition(wa.x + wa.width - 400, wa.y + wa.height - 460);
      } },
    { type: "separator" },
    { label: "退出", click: () => { quitting = true; app.quit(); } },
  ]));
}

async function pollLoop() {
  if (quitting) return;
  let m;
  try {
    m = await src.poll();
  } catch (e) {
    return; // 单次采样失败静默跳过，下轮再试
  }
  let state = m.state;
  // 庆祝：会话从 working 干净落地（无未读无新错误）
  if (currentState === "working" && state === "idle") {
    state = "celebrate";
    if (celebrateTimer) clearTimeout(celebrateTimer);
    celebrateTimer = setTimeout(() => pushState("idle"), 4000);
  }
  pushState(state, m);
  if (tray) tray.setToolTip(`ZCode 桌宠 v${APP_VERSION} — ${STATE_LABEL[state]}`);
}

function pushState(state, m) {
  if (state === currentState && !m) return;
  const prev = currentState;
  currentState = state;
  if (win && !win.isDestroyed()) {
    win.webContents.send("pet:state", {
      state,
      label: STATE_LABEL[state] || state,
      metrics: m ? {
        running: m.runningSessions || m.runningTools,
        unread: m.unread,
        errors: m.errors,
      } : null,
      prev,
    });
  }
}

// 帧素材下发：renderer 不能 fetch file://，经 IPC 传 Buffer
ipcMain.handle("pet:frames-load", (_e, state) => {
  const spec = (manifest.states && manifest.states[state]) ||
    manifest.states[manifest.defaults.fallbackState] ||
    { frames: ["idle.png"], fps: 1 };
  let files = [];
  if (spec.dir) {
    const dirOk = /^[A-Za-z0-9_-]+$/.test(spec.dir);
    if (!dirOk) return { fps: spec.fps || 1, frames: [] };
    const dir = path.join(SPR, spec.dir);
    files = fs.readdirSync(dir).filter((f) => /^[A-Za-z0-9_-]+\.png$/i.test(f))
      .sort().map((f) => path.join(dir, f));
  } else {
    files = (spec.frames || [])
      .filter((f) => /^[A-Za-z0-9_-]+\.png$/i.test(f))
      .map((f) => path.join(SPR, f));
  }
  const frames = [];
  for (const f of files) {
    try { frames.push(fs.readFileSync(f)); } catch (_) { }
  }
  return { fps: spec.fps || 1, frames };
});

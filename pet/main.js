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
let followZcode = true;   // 随 ZCode 启停：进程消失连续 2 次采样 → 退出
let missCount = 0;
const src = new StateSource();

// 状态动画时长（celebrate 一次性播放按帧数/fps 精确计算）
function stateDurationMs(state) {
  const spec = manifest.states && manifest.states[state];
  if (!spec) return 4000;
  try {
    let count = 0;
    if (spec.dir) {
      count = fs.readdirSync(path.join(SPR, spec.dir))
        .filter((f) => /\.png$/i.test(f)).length;
    } else {
      count = (spec.frames || []).length;
    }
    return Math.max(1500, Math.round(count * 1000 / (spec.fps || 24)));
  } catch (_) {
    return 4000;
  }
}

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
    { label: "随 ZCode 启停（关闭时自动退出）", type: "checkbox",
      checked: followZcode,
      click: (item) => { followZcode = item.checked; missCount = 0; } },
    { label: "回到右下角", click: () => {
        const wa = screen.getPrimaryDisplay().workArea;
        if (win && !win.isDestroyed()) {
          win.setPosition(wa.x + wa.width - 400, wa.y + wa.height - 460);
          win.show();
        }
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
  // 随 ZCode 启停：进程消失连续 2 次（约 4s）→ 跟随退出；重新检出 → 显示
  if (followZcode) {
    if (!m.process) {
      missCount++;
      if (missCount >= 2) {
        logLine("ZCode 已退出，桌宠跟随退出");
        app.quit();
        return;
      }
    } else {
      missCount = 0;
      if (win && !win.isDestroyed() && !win.isVisible()) {
        win.show();
        ensureOnScreen();
      }
    }
  }
  // 庆祝：会话从 working/walk 干净落地（无未读无新错误）
  if ((currentState === "working" || currentState === "walk") && state === "idle") {
    state = "celebrate";
    if (celebrateTimer) clearTimeout(celebrateTimer);
    celebrateTimer = setTimeout(() => pushState("idle"), stateDurationMs("celebrate"));
  }
  pushState(state, m);
  if (tray) tray.setToolTip(`ZCode 桌宠 v${APP_VERSION} — ${STATE_LABEL[state]}`);
}

// 状态帧尺寸（PNG IHDR 直读），用于按构图自适应窗口
const frameSizeCache = {};
function stateFrameSize(state) {
  if (frameSizeCache[state]) return frameSizeCache[state];
  const spec = manifest.states && manifest.states[state];
  let p = null;
  try {
    if (spec && spec.dir) {
      const dir = path.join(SPR, spec.dir);
      const f = fs.readdirSync(dir).filter((f) => /\.png$/i.test(f))
        .sort().map((f) => path.join(dir, f))[0];
      if (f) p = f;
    } else if (spec && spec.frames && spec.frames[0]) {
      p = path.join(SPR, spec.frames[0]);
    }
  } catch (_) { }
  if (!p) return { w: 384, h: 384 };
  const b = fs.readFileSync(p);
  const r = { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
  frameSizeCache[state] = r;
  return r;
}

// 窗口按状态构图自适应（底边锚定，不跳位）
function resizeWindowFor(state) {
  if (!win || win.isDestroyed()) return;
  const { w: fw, h: fh } = stateFrameSize(state);
  const scale = Math.min(330 / fw, 300 / fh);
  const W = Math.max(240, Math.round(fw * scale) + 28);
  const H = Math.max(220, Math.round(fh * scale) + 58);
  const [ow, oh] = win.getSize();
  if (Math.abs(ow - W) < 4 && Math.abs(oh - H) < 4) return;
  const [cx, cy] = win.getPosition();
  const wa = screen.getPrimaryDisplay().workArea;
  let nx = cx + ow - W;                       // 保持右下角锚定
  let ny = cy + oh - H;
  nx = Math.min(Math.max(nx, wa.x), wa.x + wa.width - W);
  ny = Math.min(Math.max(ny, wa.y), wa.y + wa.height - H);
  win.setPosition(nx, ny);
  win.setSize(W, H);
}

function pushState(state, m) {
  if (state === currentState && !m) return;
  const prev = currentState;
  currentState = state;
  resizeWindowFor(state);
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
  return { fps: spec.fps || 1, frames, once: !!spec.once };
});

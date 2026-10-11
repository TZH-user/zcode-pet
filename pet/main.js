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
  let px = wa.x + wa.width - 400, py = wa.y + wa.height - 460;
  try {   // 位置记忆：跨重启还原（双屏用户拖到副屏后不再跑回主屏）
    const saved = JSON.parse(fs.readFileSync(path.join(app.getPath("userData"), "window-pos.json"), "utf8"));
    if (Number.isFinite(saved.x) && Number.isFinite(saved.y)) { px = saved.x; py = saved.y; }
  } catch (_) { }
  win = new BrowserWindow({
    width: 380,
    height: 430,
    x: px,
    y: py,
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
  win.on("moved", () => {
    ensureOnScreen();
    try {
      fs.writeFileSync(path.join(app.getPath("userData"), "window-pos.json"),
        JSON.stringify(win.getPosition()));
    } catch (_) { }
  });
}

function ensureOnScreen() {
  if (!win || win.isDestroyed()) return;
  // 用窗口所在屏幕的 workArea（双屏不同分辨率下不能用主屏，混合 DPI 会把窗口顶出屏）
  const disp = screen.getDisplayNearestPoint(win.getBounds());
  const wa = disp.workArea;
  const [x, y] = win.getPosition();
  const [w, h] = win.getSize();
  const nx = Math.min(Math.max(x, wa.x - w + 60), wa.x + wa.width - 60);
  const ny = Math.min(Math.max(y, wa.y - h + 60), wa.y + wa.height - 60);
  if (nx !== x || ny !== y) {
    logLine(`ensureOnScreen: (${x},${y}) -> (${nx},${ny})`);
    win.setPosition(nx, ny);
  }
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

// 状态帧尺寸（PNG IHDR 直读）——仅供调试观察；窗口尺寸恒定（混合 DPI 下动态
// 缩放窗口会踩 Electron setPosition/setSize 坑把窗口顶出屏，宽构图由渲染端适配）
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
  return { fps: spec.fps || 1, frames, once: !!spec.once };
});

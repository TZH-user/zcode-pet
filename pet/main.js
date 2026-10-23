// ZCode 桌宠 主进程：透明置顶窗口 + 会话状态轮询 + 帧素材 IPC
// 经验规避：禁 GPU 加速防透明立绘丢失；异常落盘不弹窗；单实例锁
"use strict";
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const { StateSource, STATE_LABEL, zcodeRunning } = require("./zcode_state");

// ---------- 随 ZCode 启停的时延参数 ----------
// 原实现把"跟随退出"和数据轮询绑在同一个 2s 定时器里，要连续 2 次未检出才退出，
// 最坏 ~4s + tasklist 开销。要压缩时延不能简单缩短 pollLoop —— 它每次要打开
// 334MB 的 db.sqlite + tasks-index.sqlite，频率翻倍纯属浪费。因此拆成两个回路：
//   procLoop  900ms  只跑 tasklist（廉价）→ 跟随退出，最坏 ~1.8s
//   pollLoop 2000ms  跑 SQLite 数据 + 推状态 + 庆祝逻辑
const PROC_POLL_MS = 900;
const DATA_POLL_MS = 2000;
const EXIT_MISS_LIMIT = 2;      // 连续 2 次未检出才退出（防 tasklist 抖动误杀）
const STARTUP_GRACE_MS = 6000;  // 启动宽限：登录自启/快速重启竞态下不立刻自杀

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
let followZcode = true;   // 随 ZCode 启停：进程消失连续 EXIT_MISS_LIMIT 次 → 退出
let missCount = 0;
let startedAt = Date.now();   // 启动宽限计时起点（STARTUP_GRACE_MS 内不计 miss）
let dragging = false;     // 长按拖动中：位置记忆延迟到拖动结束
const src = new StateSource();

// ---------- 设置（右键菜单可改，落盘 userData/settings.json）----------
// showShadow / showGround 默认 false：这两处半透明自绘 + label 深色药丸
// 就是用户一直抱怨的"背景色没去掉"，默认关掉即完全透明浮空。
const SETTINGS_PATH = () => path.join(app.getPath("userData"), "settings.json");
// 运行标记：写自己的 PID，供外部看门狗判断"桌宠是否在跑"。
// 不能靠 Get-Process -Name electron 判断——本机同时跑着 ZCode / WorkBuddy /
// opencode 桌面版 / Tabbit 等多个 Electron 应用，只看进程名会永远误判为"在跑"。
const LOCK_PATH = () => path.join(app.getPath("userData"), "pet.lock");
const HOLD_PATH = () => path.join(app.getPath("userData"), "no-autostart");

function writeLock() {
  try {
    fs.writeFileSync(LOCK_PATH(), String(process.pid));
  } catch (_) { }
}
function clearLock() {
  try { fs.unlinkSync(LOCK_PATH()); } catch (_) { }
}
// 用户从菜单点"退出"时写这个标记，否则外部看门狗会在几秒内把桌宠再拉起来。
// 手动启动桌宠会清掉它 —— 语义就是"我手动开的，那就恢复自动跟随"。
function holdAutostart() {
  try {
    fs.writeFileSync(HOLD_PATH(), new Date().toISOString());
  } catch (_) { }
}
function clearHold() {
  try { fs.unlinkSync(HOLD_PATH()); } catch (_) { }
}
const DEFAULT_SETTINGS = {
  showLabel: true,      // 状态文字（无底色，改用描边）
  showShadow: false,    // 脚下椭圆软阴影
  showGround: false,    // 踱步/跑步的地面滚动短线
  showMetrics: false,   // 调试指标面板
  speed: 1.0,           // 动画速度倍率
  followZcode: true,
  forceState: "",       // 非空 = 强制状态（调试），空 = 跟随真实状态
  settingsVersion: 0,   // 每次"重新加载帧"+1，渲染端据此丢缓存重解码
};
let settings = { ...DEFAULT_SETTINGS };

function loadSettings() {
  try {
    // 剥 BOM：Node 的 readFileSync(path,"utf8") 不去 BOM，JSON.parse("\uFEFF{...}")
    // 直接抛错。而 Windows 上 PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写
    // BOM（本项目反复踩的 PS5.1 编码坑，见记忆条目 5/20），一旦中招 catch 会静默
    // 吞掉并回落默认值 —— 表现为"右键菜单改了没反应"，极难排查。
    let raw = fs.readFileSync(SETTINGS_PATH(), "utf8");
    if (raw.charCodeAt(0) === 0xFEFF) raw = raw.slice(1);
    settings = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch (_) { settings = { ...DEFAULT_SETTINGS }; }
  followZcode = !!settings.followZcode;
  const sp = Number(settings.speed);
  settings.speed = Number.isFinite(sp) && sp > 0 ? Math.min(3, Math.max(0.25, sp)) : 1;
}

function saveSettings() {
  settings.followZcode = followZcode;
  try {
    fs.writeFileSync(SETTINGS_PATH(), JSON.stringify(settings, null, 2));
  } catch (e) { logLine("saveSettings failed: " + e); }
}

function pushSettings() {
  if (win && !win.isDestroyed()) win.webContents.send("pet:settings", { ...settings });
}

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
  // loadSettings 必须留在 whenReady 回调里：bootstrap() 在模块顶层（第 27 行）
  // 被同步调用，而 DEFAULT_SETTINGS 是第 44 行的 const——放在这里直接引用会踩
  // TDZ（"Cannot access 'DEFAULT_SETTINGS' before initialization"），app.whenReady()
  // 的回调要等模块求值完成才跑，届时 const 已初始化。
  app.whenReady().then(() => {
    loadSettings();
    clearHold();      // 手动启动 = 恢复自动跟随（否则看门狗会一直绕着 no-autostart 打转）
    writeLock();
    createWindow();
    ensureOnScreen();          // 位置记忆可能还原出屏外坐标，启动时先拉回屏内
    createTray();
    setInterval(pollLoop, DATA_POLL_MS);   // 数据轮询（SQLite，开销大）
    setInterval(procLoop, PROC_POLL_MS);   // 进程存活探测（tasklist，开销小）
    setTimeout(pollLoop, 300);
    setTimeout(procLoop, 300);
    startDebugCapture();       // PET_DEBUG=1 → 每 3s capturePage 落盘
  });
  app.on("second-instance", () => {
    if (win && !win.isDestroyed()) { win.show(); ensureOnScreen(); }
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => { quitting = true; clearLock(); });
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
      backgroundThrottling: false,   // 被遮挡/失焦也持续动画（贴纸性质，别让 rAF 被节流成静止）
    },
  });
  win.setAlwaysOnTop(true, "screen-saver");
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  win.webContents.on("console-message", (_e, level, message, line, sourceId) => {
    if (level >= 2) logLine(`renderer[${level}] ${message} (${path.basename(String(sourceId))}:${line})`);
  });
  win.webContents.on("render-process-gone", (_e, details) => logLine("render-gone: " + JSON.stringify(details)));
  win.webContents.on("did-fail-load", (_e, code, desc) => logLine(`did-fail-load ${code} ${desc}`));
  win.webContents.on("did-finish-load", () => pushSettings());
  win.on("moved", () => {
    ensureOnScreen();
    if (dragging) return;   // 拖动中不逐帧写盘，结束统一写
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

// 右键菜单 / 托盘菜单共用的模板（单一事实来源，改一处两边同步）
const FORCE_STATES = ["idle", "walk", "working", "waiting", "error", "notification", "sleeping", "celebrate"];
const SPEEDS = [
  { label: "慢 0.5×", value: 0.5 },
  { label: "标准 1×", value: 1 },
  { label: "快 1.5×", value: 1.5 },
  { label: "很快 2×", value: 2 },
];

function buildMenuTemplate() {
  return [
    { label: "ZCode 桌宠 v" + APP_VERSION, enabled: false },
    { type: "separator" },

    // ---- 强制状态（调试）----
    { label: "强制状态", submenu: [
      { label: "跟随真实状态", type: "radio", checked: !settings.forceState,
        click: () => { settings.forceState = ""; saveSettings(); pushSettings(); pushState(currentState, null); } },
      { type: "separator" },
      ...FORCE_STATES.map((s) => ({
        label: (STATE_LABEL[s] || s) + "（" + s + "）",
        type: "radio",
        checked: settings.forceState === s,
        click: () => { settings.forceState = s; saveSettings(); pushSettings(); pushState(s, null); },
      })),
    ] },

    // ---- 调试 ----
    { label: "调试指标面板", type: "checkbox", checked: !!settings.showMetrics,
      click: (item) => setOption("showMetrics", item.checked) },
    { label: "重新加载帧（丢解码缓存）", click: () => { settings.settingsVersion++; saveSettings(); pushSettings(); } },
    { label: "立即截图（capturePage）", click: () => captureNow("manual") },
    { label: "打开素材目录", click: () => shellOpenPath(SPR) },
    { label: "打开日志", click: () => shellOpenPath(path.join(process.env.TEMP || ".", "zcode-pet.log")) },

    { type: "separator" },

    // ---- 外观 ----
    { label: "状态文字", type: "checkbox", checked: !!settings.showLabel,
      click: (item) => setOption("showLabel", item.checked) },
    { label: "落地阴影", type: "checkbox", checked: !!settings.showShadow,
      click: (item) => setOption("showShadow", item.checked) },
    { label: "地面滚动线", type: "checkbox", checked: !!settings.showGround,
      click: (item) => setOption("showGround", item.checked) },
    { label: "动画速度", submenu: SPEEDS.map((sp) => ({
      label: sp.label, type: "radio", checked: Math.abs((settings.speed || 1) - sp.value) < 1e-6,
      click: () => setOption("speed", sp.value),
    })) },

    { type: "separator" },

    // ---- 行为 ----
    { label: "随 ZCode 启停（关闭时自动退出）", type: "checkbox",
      checked: followZcode,
      click: (item) => { followZcode = item.checked; missCount = 0; saveSettings(); syncTrayMenu(); } },
    { label: "回到右下角", click: () => {
        const wa = screen.getPrimaryDisplay().workArea;
        if (win && !win.isDestroyed()) {
          win.setPosition(wa.x + wa.width - 400, wa.y + wa.height - 460);
          win.show();
        }
      } },
    { label: "退出（本次不再自动拉起）", click: () => { quitting = true; holdAutostart(); app.quit(); } },
    { label: "退出并清除“不自动拉起”标记", click: () => { quitting = true; clearHold(); app.quit(); } },
  ];
}

function setOption(key, value) {
  settings[key] = value;
  saveSettings();
  pushSettings();
  syncTrayMenu();
}

function syncTrayMenu() {
  if (tray && !tray.isDestroyed()) tray.setContextMenu(Menu.buildFromTemplate(buildMenuTemplate()));
}

function createTray() {
  const iconPath = path.join(__dirname, "build", "icon.ico");
  tray = new Tray(iconPath);
  tray.setToolTip("ZCode 桌宠 v" + APP_VERSION);
  syncTrayMenu();
}

// 右键桌宠：由渲染端 contextmenu → IPC 主动请求（frameless + drag region 下
// webContents 'context-menu' 事件不保证触发，所以走 IPC 主动 popup）
ipcMain.on("pet:open-menu", () => {
  if (!win || win.isDestroyed()) return;
  Menu.buildFromTemplate(buildMenuTemplate()).popup({ window: win });
});

ipcMain.on("pet:reload-frames", () => {
  settings.settingsVersion++;
  saveSettings();
  pushSettings();
});

ipcMain.on("pet:set-option", (_e, key, value) => {
  if (!Object.prototype.hasOwnProperty.call(DEFAULT_SETTINGS, key)) return;
  setOption(key, value);
});

ipcMain.handle("pet:get-settings", () => ({ ...settings }));

// ---------- 视觉 QC：capturePage 是透明分层窗口唯一可信的取证手段 ----------
// CopyFromScreen / PrintWindow 对透明窗口会丢透明像素（记忆条目 14/28）。
function captureNow(tag) {
  if (!win || win.isDestroyed()) return;
  const dir = path.join(process.env.TEMP || ".", "pet-shots");
  win.webContents.capturePage().then((img) => {
    try {
      fs.mkdirSync(dir, { recursive: true });
      const p = path.join(dir, "capture.png");
      fs.writeFileSync(p, img.toPNG());
      logLine(`capture[${tag}] -> ${p}`);
    } catch (e) { logLine("capture failed: " + e); }
  }).catch((e) => logLine("capturePage failed: " + e));
}

function startDebugCapture() {
  if (process.env.PET_DEBUG !== "1") return;
  logLine("PET_DEBUG=1 → 每 3s capturePage 落盘 %TEMP%\\pet-shots\\capture.png");
  setTimeout(() => captureNow("auto"), 1500);
  setInterval(() => captureNow("auto"), 3000);
}

function shellOpenPath(p) {
  if (!p) return;
  try {
    if (!fs.existsSync(p)) { logLine("shell.openPath 目标不存在: " + p); return; }
    shell.openPath(p);
  } catch (e) { logLine("shell.openPath failed: " + e); }
}

// 随 ZCode 启停的廉价回路：只跑 tasklist，不碰 SQLite。
// 与 pollLoop 分开的原因见文件头 PROC_POLL_MS 的注释——单纯缩短 pollLoop
// 会把 334MB 的 db.sqlite 打开频率翻倍。
// 退出时延：最坏 (PROC_POLL_MS * EXIT_MISS_LIMIT) + tasklist 开销 ≈ 1.8s
//           修复前是 (2000 * 2) + 开销 ≈ 4~5s
function procLoop() {
  if (quitting) return;
  if (!followZcode) return;              // 不跟随就完全不探测，省掉 tasklist 开销
  zcodeRunning().then((up) => {
    if (quitting) return;
    if (up) {
      missCount = 0;
      if (win && !win.isDestroyed() && !win.isVisible()) {
        win.show();
        ensureOnScreen();
      }
      return;
    }
    // 启动宽限：登录自启或 ZCode 快速重启的竞态下，别刚起来就自杀
    if (Date.now() - startedAt < STARTUP_GRACE_MS) return;
    missCount++;
    if (missCount >= EXIT_MISS_LIMIT) {
      logLine(`ZCode 已退出，桌宠跟随退出（连续 ${missCount} 次未检出）`);
      quitting = true;
      app.quit();
    }
  }).catch(() => { /* 单次探测失败静默跳过，下轮再试 */ });
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
  // 强制状态优先级：右键菜单设置 > 环境变量（诊断用）> 真实轮询结果
  if (settings.forceState) state = settings.forceState;
  else if (process.env.PET_FORCE_STATE) state = process.env.PET_FORCE_STATE;
  // 庆祝：会话从 working/walk 干净落地（无未读无新错误）
  // 强制状态时不触发——否则选 walk→idle 会被 celebrate 覆盖，调试菜单失效
  if (!settings.forceState && !process.env.PET_FORCE_STATE &&
      (currentState === "working" || currentState === "walk") && state === "idle") {
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

// 拖动窗口：只 setPosition 不动尺寸（混合 DPI 下 setSize 会把窗口顶出屏，之前踩过），
// 增量是 renderer CSS 像素 = 窗口 DIP 坐标，Electron 自动映射各屏 DPI
ipcMain.on("pet:move-by", (_e, dx, dy) => {
  if (!win || win.isDestroyed()) return;
  dragging = true;
  const [x, y] = win.getPosition();
  win.setPosition(x + Math.round(dx), y + Math.round(dy));
});
ipcMain.on("pet:end-drag", () => {
  if (!dragging) return;
  dragging = false;
  ensureOnScreen();
  try {
    fs.writeFileSync(path.join(app.getPath("userData"), "window-pos.json"),
      JSON.stringify(win.getPosition()));
  } catch (_) { }
});

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

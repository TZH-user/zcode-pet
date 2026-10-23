// 帧动画引擎：IPC 收 Buffer → createImageBitmap → 按状态 fps 循环绘制
// 经验：只保留当前状态帧，切状态即释放；canvas 定格最后一帧防白闪
//
// 接管会话（2026-10-13）改动：
//  ① 去掉"背景色"三处自绘半透明：脚下椭圆阴影 / 地面滚动短线 / label 深色药丸
//     （药丸底已移到 CSS 改为无底+描边；阴影与地面线改为设置项，默认关闭）
//  ② 右键桌宠 → window.pet.openMenu()，菜单本体在主进程
//  ③ 设置项：showLabel / showShadow / showGround / speed / showMetrics
//  ④ 拖拽只认左键，避免右键触发戳击与拖动
"use strict";
const cv = document.getElementById("sprite");
const ctx = cv.getContext("2d");
const label = document.getElementById("label");
const metricsEl = document.getElementById("metrics");

let cur = { state: null, bitmaps: [], fps: 1, once: false, startedAt: 0 };
let prev = null;        // 上一状态解码缓存：来回切换免重解码（切换瞬间的静止即加载期）
let pokeUntil = 0;
let drag = null;

// 主进程下发的设置；getSettings 未返回前用这套保守默认值（= 无背景色）
const settings = {
  showLabel: true,
  showShadow: false,
  showGround: false,
  showMetrics: false,
  speed: 1.0,
  settingsVersion: 0,
};
let lastVersion = -1;

function cleanup() {
  for (const b of cur.bitmaps) { try { b.close(); } catch (_) { } }
  cur.bitmaps = [];
}

async function setState(name) {
  if (cur.state === name) return;
  if (prev && prev.state === name) {          // 命中缓存：直接换入
    cleanup();
    const old = cur;
    cur = { state: prev.state, bitmaps: prev.bitmaps, fps: prev.fps,
            once: prev.once, startedAt: performance.now() };
    prev = { state: old.state, bitmaps: old.bitmaps, fps: old.fps, once: old.once };
    return;
  }
  const res = await window.pet.loadFrames(name);
  if (!res.frames.length) return;
  const bitmaps = [];
  for (const buf of res.frames) {
    try { bitmaps.push(await createImageBitmap(new Blob([buf], { type: "image/png" }))); }
    catch (_) { }
  }
  if (!bitmaps.length) return;
  if (prev) for (const b of prev.bitmaps) { try { b.close(); } catch (_) { } }
  prev = { state: cur.state, bitmaps: cur.bitmaps, fps: cur.fps, once: cur.once };
  cur = { state: name, bitmaps, fps: Math.max(0.1, res.fps || 1),
          once: !!res.once, startedAt: performance.now() };
}

function fitCanvas() {
  cv.width = window.innerWidth;
  cv.height = window.innerHeight;
}
window.addEventListener("resize", fitCanvas);
fitCanvas();

function draw() {
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  if (cur.bitmaps.length) {
    const fps = cur.fps * (settings.speed || 1);
    let idx = cur.bitmaps.length > 1
      ? Math.floor((performance.now() - cur.startedAt) / 1000 * fps) % cur.bitmaps.length
      : 0;
    if (cur.once && (performance.now() - cur.startedAt) / 1000 * fps >= cur.bitmaps.length) {
      idx = cur.bitmaps.length - 1;   // 一次性动画播完定格末帧
    }
    const bmp = cur.bitmaps[idx];
    if (Math.random() < 0.02) console.warn("[diag]", cur.state, "frame", idx, "/", cur.bitmaps.length, "fps", fps);
    // 等比缩放：目标高 300，且不超出画布宽度
    const scale = Math.min(300 / bmp.height, (W - 20) / bmp.width);
    let w = bmp.width * scale, h = bmp.height * scale;
    if (performance.now() < pokeUntil) {
      const k = 0.9;
      w /= k; h *= k;
    }
    const x = (W - w) / 2, y = H - h - 6;
    // 地面：椭圆软阴影 + 踱步/跑步的滚动短线 + 速度线。
    // 这三处是"背景色"的真正来源，默认全部关闭（可在右键菜单里开回来）。
    if (settings.showGround && (cur.state === "walk" || cur.state === "working")) {
      const t = performance.now() / 1000;
      ctx.strokeStyle = "rgba(120,130,150,0.35)";
      ctx.lineWidth = 2;
      const dir = cur.state === "working" ? -1 : 1;   // 跑步向右，地纹向左滚
      for (let i = 0; i < 3; i++) {
        const gx = (W / 2 + dir * (((t * 60) + i * 46) % 150) - 75);
        const gy = H - 14 + (i % 2) * 4;
        ctx.beginPath();
        ctx.moveTo(gx - 12, gy);
        ctx.lineTo(gx + 12, gy);
        ctx.stroke();
      }
    }
    if (settings.showShadow) {
      ctx.fillStyle = "rgba(30,32,44,0.20)";
      ctx.beginPath();
      ctx.ellipse(W / 2, H - 10, w * 0.26, 7, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.drawImage(bmp, x, y, w, h);
  }
  requestAnimationFrame(draw);
}

// ---------- 设置应用 ----------
function applySettings(next) {
  Object.assign(settings, next || {});
  if (label) label.classList.toggle("hidden", !settings.showLabel);
  if (metricsEl) metricsEl.classList.toggle("hidden", !settings.showMetrics);
  // 版本号变化 = 用户点了"重新加载帧"：丢掉解码缓存强制重取
  if (settings.settingsVersion !== lastVersion) {
    lastVersion = settings.settingsVersion;
    if (cur.state) {
      const keep = cur.state;
      cleanup();
      for (const b of prev ? prev.bitmaps : []) { try { b.close(); } catch (_) { } }
      prev = null;
      cur.state = null;
      setState(keep);
    }
  }
}

window.pet.onSettings((s) => applySettings(s));
window.pet.getSettings().then(applySettings).catch(() => { });

window.pet.onState((s) => {
  label.textContent = s.label;
  label.className = settings.showLabel ? s.state : "hidden";
  setState(s.state);
  if (metricsEl && settings.showMetrics) {
    const m = s.metrics || {};
    metricsEl.textContent =
      `state   ${s.state}\n` +
      `running ${m.running != null ? m.running : "-"}\n` +
      `unread  ${m.unread != null ? m.unread : "-"}\n` +
      `errors  ${m.errors != null ? m.errors : "-"}\n` +
      `frames  ${cur.bitmaps.length} @ ${(cur.fps * (settings.speed || 1)).toFixed(1)}fps`;
  }
});

// ---------- 交互 ----------
cv.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;          // 只认左键：右键归菜单，别触发拖拽/戳击
  drag = { lx: e.clientX, ly: e.clientY, moved: false };   // 长按拖动：移动>4px 判定为拖而非戳
});

window.addEventListener("mousemove", (e) => {
  if (!drag) return;
  if (!drag.moved && Math.hypot(e.clientX - drag.lx, e.clientY - drag.ly) > 4) {
    drag.moved = true;
    document.body.style.cursor = "grabbing";
  }
  if (drag.moved) {
    window.pet.moveBy(e.clientX - drag.lx, e.clientY - drag.ly);
    drag.lx = e.clientX; drag.ly = e.clientY;
  }
});

window.addEventListener("mouseup", () => {
  if (drag && !drag.moved) pokeUntil = performance.now() + 260;   // 点击压扁-回弹
  if (drag && drag.moved) window.pet.endDrag();   // 拖动结束：主进程统一做屏内钳制+写位置记忆
  drag = null;
  document.body.style.cursor = "";
});

// 右键 → 主进程弹菜单（frameless + drag region 事件不可靠，走 IPC 最稳）
window.addEventListener("contextmenu", (e) => {
  e.preventDefault();
  window.pet.openMenu();
});

requestAnimationFrame(draw);
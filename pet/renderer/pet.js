// 帧动画引擎：IPC 收 Buffer → createImageBitmap → 按状态 fps 循环绘制
// 经验：只保留当前状态帧，切状态即释放；canvas 定格最后一帧防白闪
"use strict";
const cv = document.getElementById("sprite");
const ctx = cv.getContext("2d");
const label = document.getElementById("label");

let cur = { state: null, bitmaps: [], fps: 1, once: false, startedAt: 0 };
let prev = null;        // 上一状态解码缓存：来回切换免重解码（切换瞬间的静止即加载期）
let pokeUntil = 0;
let drag = null;

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
    let idx = cur.bitmaps.length > 1
      ? Math.floor((performance.now() - cur.startedAt) / 1000 * cur.fps) % cur.bitmaps.length
      : 0;
    if (cur.once && (performance.now() - cur.startedAt) / 1000 * cur.fps >= cur.bitmaps.length) {
      idx = cur.bitmaps.length - 1;   // 一次性动画播完定格末帧
    }
    const bmp = cur.bitmaps[idx];
    if (Math.random() < 0.02) console.warn("[diag]", cur.state, "frame", idx, "/", cur.bitmaps.length, "fps", cur.fps);
    // 等比缩放：目标高 300，且不超出画布宽度
    const scale = Math.min(300 / bmp.height, (W - 20) / bmp.width);
    let w = bmp.width * scale, h = bmp.height * scale;
    if (performance.now() < pokeUntil) {
      const k = 0.9;
      w /= k; h *= k;
    }
    const x = (W - w) / 2, y = H - h - 6;
    // 地面：椭圆软阴影（所有状态）；踱步/跑步加滚动地面短线与速度线
    if (cur.state === "walk" || cur.state === "working") {
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
    ctx.fillStyle = "rgba(30,32,44,0.20)";
    ctx.beginPath();
    ctx.ellipse(W / 2, H - 10, w * 0.26, 7, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.drawImage(bmp, x, y, w, h);
  }
  requestAnimationFrame(draw);
}

window.pet.onState((s) => {
  label.textContent = s.label;
  label.className = s.state;
  setState(s.state);
});

cv.addEventListener("mousedown", (e) => {
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

requestAnimationFrame(draw);

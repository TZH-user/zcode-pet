// 帧动画引擎：IPC 收 Buffer → createImageBitmap → 按状态 fps 循环绘制
// 经验：只保留当前状态帧，切状态即释放；canvas 定格最后一帧防白闪
"use strict";
const cv = document.getElementById("sprite");
const ctx = cv.getContext("2d");
const label = document.getElementById("label");

let cur = { state: null, bitmaps: [], fps: 1, once: false, startedAt: 0 };
let pokeUntil = 0;

function cleanup() {
  for (const b of cur.bitmaps) { try { b.close(); } catch (_) { } }
  cur.bitmaps = [];
}

async function setState(name) {
  if (cur.state === name) return;
  const res = await window.pet.loadFrames(name);
  if (!res.frames.length) return;
  const bitmaps = [];
  for (const buf of res.frames) {
    try { bitmaps.push(await createImageBitmap(new Blob([buf], { type: "image/png" }))); }
    catch (_) { }
  }
  if (!bitmaps.length) return;
  cleanup();
  cur = { state: name, bitmaps, fps: Math.max(0.1, res.fps || 1),
          once: !!res.once, startedAt: performance.now() };
}

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
    const targetH = 300;
    const scale = targetH / bmp.height;
    let w = bmp.width * scale, h = targetH;
    if (performance.now() < pokeUntil) {
      const k = 0.9;
      w *= 1 / k; h *= k;
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

cv.addEventListener("mousedown", () => {
  pokeUntil = performance.now() + 260;   // 压扁-回弹
});

requestAnimationFrame(draw);

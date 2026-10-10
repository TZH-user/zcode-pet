// 帧动画引擎：IPC 收 Buffer → createImageBitmap → 按状态 fps 循环绘制
// 经验：只保留当前状态帧，切状态即释放；canvas 定格最后一帧防白闪
"use strict";
const cv = document.getElementById("sprite");
const ctx = cv.getContext("2d");
const label = document.getElementById("label");

let cur = { state: null, bitmaps: [], fps: 1, startedAt: 0 };
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
  cur = { state: name, bitmaps, fps: Math.max(0.1, res.fps || 1), startedAt: performance.now() };
}

function draw() {
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  if (cur.bitmaps.length) {
    let idx = cur.bitmaps.length > 1
      ? Math.floor((performance.now() - cur.startedAt) / 1000 * cur.fps) % cur.bitmaps.length
      : 0;
    const bmp = cur.bitmaps[idx];
    const targetH = 300;
    const scale = targetH / bmp.height;
    let w = bmp.width * scale, h = targetH;
    // 戳击压扁回弹
    if (performance.now() < pokeUntil) {
      const k = 0.9;
      w *= 1 / k; h *= k;
    }
    ctx.drawImage(bmp, (W - w) / 2, H - h - 4, w, h);
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

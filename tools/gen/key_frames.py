# -*- coding: utf-8 -*-
"""视频帧白底键控 → 时序平滑 → 统一 bbox 输出透明帧序列。

针对 Animate2 产出的纯白底角色动画帧：
  1. 逐帧连通域洪泛抠白底（与 tools/bg_remove.py 同原理，封闭浅色自动保护）
  2. alpha 时序平滑（0.25/0.5/0.25 核）消除逐帧抖动闪烁
  3. 全帧取并集 bbox 统一裁剪——角色位置逐帧稳定，桌宠不跳动

用法: python tools/gen/key_frames.py <帧目录|视频> <输出目录> [--tol 30] [--sat 30]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def load_frames(src: Path, tmp: Path):
    if src.is_file():
        d = tmp / "frames"
        d.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        str(d / "f_%04d.png")], check=True)
        return sorted(d.glob("*.png"))
    return sorted(list(src.glob("*.png")) + list(src.glob("*.jpg")))


def matte_frame(rgb: np.ndarray, tol: float, sat_max: float) -> np.ndarray:
    """返回 [H,W] float32 alpha (0..1)。边界连通白底清除 + 边缘羽化。"""
    bg = np.array([252.5, 252.5, 252.5])
    d = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    bg_like = (d <= tol) & (sat <= sat_max)
    labels, _ = ndimage.label(bg_like)
    border_ids = set(np.unique(labels[0, :])) | set(np.unique(labels[-1, :])) \
        | set(np.unique(labels[:, 0])) | set(np.unique(labels[:, -1]))
    border_ids.discard(0)
    holes = np.isin(labels, list(border_ids)) if border_ids else np.zeros_like(bg_like)
    alpha = np.where(holes, 0.0, 1.0)
    band = ndimage.binary_dilation(holes, iterations=2) & ~holes
    ramp = np.clip((d - tol * 0.5) / (tol * 1.5), 0.0, 1.0)
    alpha[band] = np.minimum(alpha[band], ramp[band])
    return alpha


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--tol", type=float, default=30.0)
    ap.add_argument("--sat", type=float, default=30.0)
    ap.add_argument("--frames", type=int, default=0, help="只取前 N 帧（0=全部）")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = load_frames(src, Path(tempfile.mkdtemp()))
    if args.frames:
        frames = frames[:args.frames]
    assert frames, f"无输入帧: {src}"

    alphas, rgbs = [], []
    for f in frames:
        im = Image.open(f).convert("RGB")
        rgb = np.asarray(im, np.float32)
        rgbs.append(rgb)
        alphas.append(matte_frame(rgb, args.tol, args.sat))
    print(f"{len(frames)} 帧键控完成")

    # 时序平滑（首尾帧用自身补边）
    A = np.stack(alphas)
    S = np.empty_like(A)
    S[0] = 0.75 * A[0] + 0.25 * A[1]
    S[-1] = 0.75 * A[-1] + 0.25 * A[-2]
    for t in range(1, len(A) - 1):
        S[t] = 0.25 * A[t - 1] + 0.5 * A[t] + 0.25 * A[t + 1]
    S[S > 0.92] = 1.0            # 内部实心还原，防平滑侵蚀
    S[S < 0.04] = 0.0

    # 只保留主体连通域周边的 alpha：清除离体幽灵残影/角标白块
    for t in range(len(S)):
        solid = S[t] > 0.5
        if not solid.any():
            continue
        labels, n = ndimage.label(solid)
        if n > 1:
            sizes = ndimage.sum(solid, labels, range(1, n + 1))
            main = (labels == (np.argmax(sizes) + 1))
        else:
            main = solid
        keep = ndimage.binary_dilation(main, iterations=8)
        S[t] = np.where(keep, S[t], 0.0)

    # 全帧并集 bbox（统一裁剪，位置稳定）
    ys, xs = np.where(S.max(axis=0) > 0.08)
    pad = 10
    H, W = S.shape[1:]
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, H - 1)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, W - 1)
    print(f"统一 bbox=({x0},{y0})-({x1},{y1})  尺寸 {x1-x0+1}x{y1-y0+1}")

    for t, (rgb, a) in enumerate(zip(rgbs, S)):
        rgba = np.dstack([rgb / 255.0, a[..., None]])
        rgba = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(out / f"run_{t:03d}.png")
    print(f"输出 {len(frames)} 张 → {out}")


if __name__ == "__main__":
    main()

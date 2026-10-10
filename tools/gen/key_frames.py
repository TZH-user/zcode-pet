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


def ndi_sum(labels, n):
    return np.bincount(labels.ravel())[1:] if n else np.array([1])


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
    ap.add_argument("--smooth", type=float, default=0.0,
                    help="alpha 时序平滑系数 0~1（大动作设 0 防运动拖尾）")
    ap.add_argument("--killwhite", action="store_true", default=True,
                    help="压制近白半透明残影（白底视频模型的运动白雾）")
    ap.add_argument("--seamblend", type=int, default=3,
                    help="循环接缝混合：末 K 帧 RGB+alpha 向首帧线性融合（K=0 关闭）")
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

    # 时序平滑（首尾帧用自身补边）。注意：动作大时相邻帧位移大，
    # 加权平均会产生半透明运动拖尾——键控稳定的纯色底应关闭（--smooth 0）。
    A = np.stack(alphas)
    S = A.copy()
    if args.smooth > 0:
        w = args.smooth
        S[0] = (1 - w) * A[0] + w * A[1]
        S[-1] = (1 - w) * A[-1] + w * A[-2]
        for t in range(1, len(A) - 1):
            S[t] = (1 - w) * A[t] + (w / 2) * (A[t - 1] + A[t + 1])
    S[S > 0.92] = 1.0            # 内部实心还原，防平滑侵蚀
    S[S < 0.04] = 0.0

    # 只保留主体连通域周边的 alpha：清除离体幽灵残影/角标白块。
    # 残影可能与身体仅以 1~2px 细桥相连，先用开运算断桥再取主连通域。
    for t in range(len(S)):
        solid = S[t] > 0.5
        if not solid.any():
            continue
        opened = ndimage.binary_opening(solid, iterations=2)
        labels, n = ndimage.label(opened)
        if n > 0:
            sizes = ndi_sum(labels, n)
            main = (labels == (np.argmax(sizes) + 1))
            keep = ndimage.binary_dilation(main, iterations=8)
            S[t] = np.where(keep, S[t], 0.0)

    # 白雾压制：视频模型的白色运动残影（近白+半透明）在白底上不可见、
    # 抠出后成灰色重影。白裙本体是不透明的，不会被误伤。
    if args.killwhite:
        for t, rgb in enumerate(rgbs):
            mn = rgb.min(axis=2)
            sat = rgb.max(axis=2) - rgb.min(axis=2)
            near_white = (mn >= 226) & (sat <= 24)
            veil = near_white & (S[t] > 0.03) & (S[t] < 0.8)
            S[t] = np.where(veil, S[t] * 0.15, S[t])

    # 循环接缝混合：末 K 帧 RGB+alpha 向首帧线性融合，播放回绕点差分恒为 0
    if args.seamblend > 0 and len(rgbs) > args.seamblend + 1:
        K = args.seamblend
        a0 = A[0]
        rgb0 = rgbs[0] / 255.0
        for k in range(K):
            w = (k + 1) / (K + 1)
            t = len(rgbs) - K + k
            S[t] = S[t] * (1 - w) + a0 * w
            rgbs[t] = (rgbs[t] / 255.0 * (1 - w) + rgb0 * w) * 255.0

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

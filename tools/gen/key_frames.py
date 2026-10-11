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


def matte_frame(rgb: np.ndarray, tol: float, sat_max: float, bg_mode: str = "white") -> np.ndarray:
    """返回 [H,W] float32 alpha (0..1)。边界连通背景清除 + 边缘羽化。

    white: 距纯白欧氏距离（低饱和限定）；black: 亮度 L=max(r,g,b) 亮度键。
    """
    if bg_mode == "black":
        # 全局亮度键（用户定稿）：暗于阈值的黑色一律透明——不管是否连通，
        # 封闭黑洞一次清干净；角色深蓝线条 max 通道高（>=90）自动保留。
        d = rgb.max(axis=2)
        t0, t1 = tol, tol * 2.2
        return np.clip((d - t0) / (t1 - t0), 0.0, 1.0)
    else:
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
    ap.add_argument("--bg", choices=["white", "black"], default="white",
                    help="背景键控模式（black=亮度键，配纯黑底素材）")
    ap.add_argument("--crop-right", type=int, default=-1,
                    help="显式右缘裁剪 px（覆盖自动检测）")
    ap.add_argument("--crop-left", type=int, default=-1,
                    help="显式左缘裁剪 px（覆盖自动检测）")
    ap.add_argument("--crop-top", type=int, default=-1,
                    help="显式上缘裁剪 px（覆盖自动检测）")
    ap.add_argument("--crop-bottom", type=int, default=-1,
                    help="显式下缘裁剪 px（覆盖自动检测）")
    ap.add_argument("--trim-last", type=int, default=0,
                    help="丢弃末尾 N 帧（H3 尾帧偶发竖条伪影；首尾同帧构造下无损循环）")
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = load_frames(src, Path(tempfile.mkdtemp()))
    if args.frames:
        frames = frames[:args.frames]
    if args.trim_last and len(frames) > args.trim_last + 2:
        frames = frames[:len(frames) - args.trim_last]
    assert frames, f"无输入帧: {src}"

    # 自动裁边 v2：逐帧全高中列扫描，取各帧白带（黑底）/暗带（白底）最大宽度
    step = 2
    samp = [np.asarray(Image.open(f).convert("RGB"), np.float32) for f in
            frames[::max(1, len(frames) // 12)][:12]]
    h0, w0 = samp[0].shape[:2]
    crop = {"l": 0, "r": 0, "t": 0, "b": 0}
    if args.bg == "black":
        mins = np.stack([a[:, ::step].min(axis=2) for a in samp])       # N×H×W/2
        rows_mins = np.stack([a[::step, :].min(axis=2) for a in samp])  # N×H/2×W
        for i in range(len(samp)):
            cm = mins[i]      # H × (W/2)：axis0=行, axis1=列
            cnt = 0
            while cnt < cm.shape[1] and np.quantile(cm[:, cm.shape[1] - 1 - cnt], 0.97) > 150:
                cnt += 1
            crop["r"] = max(crop["r"], cnt * step + 4)
            cnt = 0
            while cnt < cm.shape[1] and np.quantile(cm[:, cnt], 0.97) > 150:
                cnt += 1
            crop["l"] = max(crop["l"], cnt * step + 4)
            rm = rows_mins[i]  # (H/2) × W：axis0=行, axis1=列
            cnt = 0
            while cnt < rm.shape[0] and np.quantile(rm[rm.shape[0] - 1 - cnt, :], 0.97) > 150:
                cnt += 1
            crop["b"] = max(crop["b"], cnt * step + 4)
            cnt = 0
            while cnt < rm.shape[0] and np.quantile(rm[cnt, :], 0.97) > 150:
                cnt += 1
            crop["t"] = max(crop["t"], cnt * step + 4)
    if args.crop_right >= 0:
        crop["r"] = args.crop_right
    if args.crop_left >= 0:
        crop["l"] = args.crop_left
    if args.crop_top >= 0:
        crop["t"] = args.crop_top
    if args.crop_bottom >= 0:
        crop["b"] = args.crop_bottom
    for k in ("r", "l", "b", "t"):
        crop[k] = min(crop[k], 220)
    if any(crop.values()):
        print(f"自动裁边: {crop}")

    alphas, rgbs = [], []
    for f in frames:
        im = Image.open(f).convert("RGB")
        rgb = np.asarray(im, np.float32)
        rgb = rgb[crop["t"]:h0 - crop["b"], crop["l"]:w0 - crop["r"]]
        rgbs.append(rgb)
        alphas.append(matte_frame(rgb, args.tol, args.sat, args.bg))
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

    # 黑底：封闭近黑洞清除（发丝间/肢体间的背景区域，边界洪泛够不到）
    if args.bg == "black":
        for t in range(len(S)):
            dark = (rgbs[t].max(axis=2) <= args.tol) & (S[t] > 0.9)
            lab, n = ndimage.label(dark)
            if n:
                sizes = np.bincount(lab.ravel())
                big_ids = np.nonzero(sizes > 400)[0]
                big_ids = big_ids[big_ids != 0]   # bincount 0 号=非暗像素全体，必须排除
                big = np.isin(lab, big_ids) if len(big_ids) else np.zeros_like(lab, bool)
                if big.any():
                    S[t] = np.where(big, 0.0, S[t])

    # 黑底：反 premultiply——半透明像素携带黑底混合色，rgb/a 还原真色去黑边
    if args.bg == "black":
        for t in range(len(rgbs)):
            m = (S[t] > 0.03) & (S[t] < 0.985)
            if m.any():
                safe = np.maximum(S[t], 0.05)
                rgbs[t] = np.where(m[..., None], np.clip(rgbs[t] / safe[..., None], 0, 255), rgbs[t])

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
            if args.bg == "black":
                # 黑底残影=暗色半透明拖尾；角色暗部（轮廓/眼）L>120 不误伤
                mx = rgb.max(axis=2)
                veil = (mx <= 90) & (S[t] > 0.03) & (S[t] < 0.8)
            else:
                mn = rgb.min(axis=2)
                sat = rgb.max(axis=2) - rgb.min(axis=2)
                veil = (mn >= 226) & (sat <= 24) & (S[t] > 0.03) & (S[t] < 0.8)
            S[t] = np.where(veil, S[t] * 0.15, S[t])

    # 循环接缝混合：末 K 帧 RGB+alpha 向首帧线性融合，播放回绕点差分恒为 0
    if args.seamblend > 0 and len(rgbs) > args.seamblend + 1:
        K = args.seamblend
        a0 = A[0]
        rgb0 = rgbs[0] / 255.0
        guard = (a0 > 0.25)[..., None]   # 仅首帧不透明区做 RGB 混合，防透明区白影
        for k in range(K):
            w = (k + 1) / (K + 1)
            t = len(rgbs) - K + k
            S[t] = S[t] * (1 - w) + a0 * w
            rgbs[t] = np.where(guard, (rgbs[t] / 255.0 * (1 - w) + rgb0 * w),
                               rgbs[t] / 255.0) * 255.0

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

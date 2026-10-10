# -*- coding: utf-8 -*-
"""
白底/纯色底静态立绘抠透明工具。

原理：与背景色相近且低饱和的像素视为"背景候选"，用 scipy 连通域标记，
只清除与图像四边界（或 --seed 指定点）连通的部分——白衣、浅发等封闭浅色
区域因不与边界连通而被自动保护。清除区边界 feather 像素带按与背景色的
颜色距离做 alpha 线性渐变，消除白边光晕。

用法：
  python tools/bg_remove.py <in.png> <out.png> [--tol 30] [--sat 30]
                            [--feather 2] [--seed x,y ...] [--dark out_dark.png]
"""
import argparse

import numpy as np
from PIL import Image
from scipy import ndimage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--tol", type=float, default=30.0, help="与背景色的欧氏距离阈值")
    ap.add_argument("--sat", type=float, default=30.0, help="饱和度(max-min)上限，低饱和才算背景")
    ap.add_argument("--feather", type=int, default=2, help="边缘 alpha 渐变带宽(px)")
    ap.add_argument("--seed", action="append", default=[], help="额外背景种子点 x,y（清封闭空白区用）")
    ap.add_argument("--dark", default="", help="同时输出深底合成图到此路径（QC 用）")
    args = ap.parse_args()

    img = Image.open(args.infile).convert("RGBA")
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    rgb = arr[..., :3]

    corners = np.concatenate([
        rgb[:40, :40].reshape(-1, 3), rgb[:40, -40:].reshape(-1, 3),
        rgb[-40:, :40].reshape(-1, 3), rgb[-40:, -40:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    print(f"背景色采样 RGB = {bg.round(1)}")

    d = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    bg_like = (d <= args.tol) & (sat <= args.sat)

    labels, n = ndimage.label(bg_like)
    border_ids = set(np.unique(labels[0, :])) | set(np.unique(labels[-1, :])) \
        | set(np.unique(labels[:, 0])) | set(np.unique(labels[:, -1]))
    border_ids.discard(0)
    keep_bg = np.isin(labels, list(border_ids)) if border_ids else np.zeros_like(bg_like)
    print(f"背景候选 {bg_like.mean()*100:.1f}%，边界连通清除 {keep_bg.mean()*100:.1f}%（候选连通域 {n} 个）")

    for s in args.seed:
        lx, ly = (int(v) for v in s.split(","))
        if bg_like[ly, lx]:
            keep_bg |= labels == labels[ly, lx]
            print(f"种子({lx},{ly}) 连通域已清除")
        else:
            print(f"警告: 种子({lx},{ly}) 不在背景相似区，忽略")

    alpha = np.where(keep_bg, 0.0, 255.0)

    if args.feather > 0:
        near_bg = ndimage.binary_dilation(keep_bg, iterations=args.feather) & ~keep_bg
        ramp = np.clip((d - args.tol * 0.5) / (args.tol * 1.5), 0.0, 1.0)
        alpha[near_bg] = np.minimum(alpha[near_bg], ramp[near_bg] * 255.0)

    out = arr.copy()
    out[..., 3] = alpha
    out[alpha == 0, :3] = bg  # 全透明像素回填背景色，防缩放时彩边
    out = out.astype(np.uint8)

    ys, xs = np.where(alpha > 8)
    pad = 12
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, w - 1)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, h - 1)
    out = out[y0:y1 + 1, x0:x1 + 1]
    Image.fromarray(out).save(args.outfile)
    print(f"输出 {args.outfile}  裁剪 bbox=({x0},{y0})-({x1},{y1})  尺寸 {out.shape[1]}x{out.shape[0]}")
    semi = ((alpha > 8) & (alpha < 247)).mean() * 100
    print(f"半透明像素占比 {semi:.2f}%")

    if args.dark:
        base = Image.new("RGBA", (out.shape[1], out.shape[0]), (32, 32, 40, 255))
        base.alpha_composite(Image.fromarray(out))
        base.convert("RGB").save(args.dark)
        print(f"深底 QC 图 {args.dark}")


if __name__ == "__main__":
    main()

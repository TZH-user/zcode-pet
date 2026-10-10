# -*- coding: utf-8 -*-
"""RVM 时序一致视频抠图（ONNX CPU），重建自旧项目验证过的参数组合。

参数要点（2026-09 旧项目实测，勿随意改）：
  - 输入 512 + downsample_ratio 0.5 是 fp32 ONNX 唯一稳定组合（768/ratio1.0 输出全零）
  - recurrent states 用 [1,1,1,1] 零占位，模型内部自动展开（自己按 S×ratio 预设会 Expand 报错）
  - --shrink 3：MinFilter 腐蚀吃掉轮廓外白雾
  - --fog 0.1：仅压 a<0.55 的深雾带，高 alpha 白裙不误伤
  - 循环点：末 4 帧 alpha 向首帧线性混合，接缝跳变归零

用法: python tools/gen/rvm_matting.py <视频.mp4|帧目录> <输出目录> [--size 512] [--shrink 3] [--fog 0.1]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter


def load_frames(src: Path, tmp: Path):
    if src.is_file():
        d = tmp / "frames"
        d.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        str(d / "f_%04d.png")], check=True)
        return sorted(d.glob("*.png"))
    return sorted(list(src.glob("*.png")) + list(src.glob("*.jpg")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--shrink", type=int, default=3)
    ap.add_argument("--fog", type=float, default=0.1)
    ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "rvm_mobilenetv3_fp32.onnx"))
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = load_frames(src, Path(tempfile.mkdtemp()))
    assert frames, f"无输入帧: {src}"
    print(f"{len(frames)} 帧")

    so = ort.SessionOptions()
    so.intra_op_num_threads = max(4, __import__("os").cpu_count() // 2)
    sess = ort.InferenceSession(args.model, so, providers=["CPUExecutionProvider"])
    IN = [i.name for i in sess.get_inputs()]
    print("模型输入:", IN)

    def states():
        # [1,1,1,1] 零占位——模型内部自动展开成 S×h×w
        return {n: np.zeros((1, 1, 1, 1), np.float32) for n in IN[1:5]}

    H = W = args.size
    ratio = np.array([0.5], np.float32)
    rec = states()
    alphas, rgbs = [], []
    for i, f in enumerate(frames):
        im = Image.open(f).convert("RGB").resize((W, H), Image.BILINEAR)
        x = np.asarray(im, np.float32) / 255.0
        x = x.transpose(2, 0, 1)[None]
        outs = sess.run(None, {IN[0]: x, **rec, IN[5]: ratio})
        fgr, pha = outs[0], outs[1]
        for j, n in enumerate(IN[1:5]):
            rec[n] = outs[2 + j]
        a = pha[0, 0]
        alphas.append(a)
        rgbs.append(fgr[0].transpose(1, 2, 0))
        if (i + 1) % 8 == 0 or i == len(frames) - 1:
            print(f"  {i+1}/{len(frames)}")

    # 循环点混合：末 4 帧 alpha 向首帧线性靠拢（末帧=首帧）
    K = 4
    for k in range(K):
        w = (k + 1) / (K + 1)          # 0.2,0.4,0.6,0.8
        alphas[-K + k] = alphas[-K + k] * (1 - w) + alphas[0] * w

    for i, (rgb, a) in enumerate(zip(rgbs, alphas)):
        a8 = (np.clip(a, 0, 1) * 255).astype(np.uint8)
        am = Image.fromarray(a8, "L")
        if args.shrink > 0:
            am = am.filter(ImageFilter.MinFilter(args.shrink * 2 + 1))
        a = np.asarray(am, np.float32) / 255.0
        if args.fog > 0:
            a = np.where(a < 0.55, a * args.fog, a)   # 深雾压制
        rgba = np.dstack([np.clip(rgb, 0, 1), a[..., None]])
        rgba = (rgba * 255).astype(np.uint8)
        ys, xs = np.where(rgba[..., 3] > 8)
        if len(ys):
            pad = 8
            y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, H - 1)
            x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, W - 1)
            rgba = rgba[y0:y1 + 1, x0:x1 + 1]
        Image.fromarray(rgba, "RGBA").save(out / f"run_{i:03d}.png")
    print(f"输出 {len(frames)} 张 → {out}")


if __name__ == "__main__":
    main()

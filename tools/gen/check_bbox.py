# -*- coding: utf-8 -*-
"""量化各状态帧的人物 bbox 占比，确认 notification 是否近景构图"""
import glob, os
import numpy as np
from PIL import Image

SPR = r"F:\Zcode\桌宠\assets\sprites\luotianyi"
for st in ["notification", "walk", "idle", "error"]:
    fs = sorted(glob.glob(os.path.join(SPR, f"frames-{st}", "*.png")))
    if not fs:
        print(st, "NO FRAMES"); continue
    a = np.asarray(Image.open(fs[0]).convert("RGBA"))
    alpha = a[..., 3] > 128
    H, W = alpha.shape
    if alpha.any():
        ys, xs = np.where(alpha.any(axis=1))[0], np.where(alpha.any(axis=0))[0]
        bh, bw = ys[-1]-ys[0]+1, xs[-1]-xs[0]+1
        print(f"{st:13s} 帧数={len(fs):3d} 尺寸={W}x{H} 人物bbox={bw}x{bh} 高度占比={bh/H:.0%} 宽度占比={bw/W:.0%}")
    else:
        print(st, "首帧全透明?")

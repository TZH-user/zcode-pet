# -*- coding: utf-8 -*-
"""分析 walk 帧序列的人物位置曲线，定位转身段（镜像翻倍的拼接点）"""
import glob, os
import numpy as np
from PIL import Image

DIR = r"F:\Zcode\桌宠\assets\sprites\luotianyi\frames-walk"
files = sorted(glob.glob(os.path.join(DIR, "run_*.png")))
print("frames:", len(files))

rows = []
for i, f in enumerate(files):
    a = np.asarray(Image.open(f).convert("RGBA"), dtype=np.uint8)
    alpha = a[..., 3] > 128
    if not alpha.any():
        rows.append((i, -1, 0)); continue
    xs = np.where(alpha.any(axis=0))[0]
    rows.append((i, (xs[0] + xs[-1]) / 2, xs[-1] - xs[0] + 1))

# 每 3 帧打印一行
for i, cx, w in rows[::3]:
    print(f"{i:4d}  cx={cx:7.1f}  w={w:4d}")

cxs = np.array([r[1] for r in rows], dtype=float)
ws = np.array([r[2] for r in rows], dtype=float)
imax = int(np.argmax(cxs))
print("\ncx max at frame", imax, "cx=", cxs[imax], "w=", ws[imax])
imin = int(np.argmin(cxs))
print("cx min at frame", imin, "cx=", cxs[imin], "w=", ws[imin])
# 宽度谷值（侧身/背身最窄处）可能在转身中段
iwmin = int(np.argmin(ws[: ws.size]))
print("w min at frame", iwmin, "w=", ws[iwmin])

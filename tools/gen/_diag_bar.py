# -*- coding: utf-8 -*-
"""诊断：working 源视频右缘白条出现范围。"""
import glob

import numpy as np
from PIL import Image

fs = sorted(glob.glob("assets/gen/src_working/f_*.png"))
print("帧数:", len(fs))
for f in fs[::6] + fs[-6:]:
    a = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
    col = a[200:600, 750:768]
    white_ratio = float((col.min(axis=2) > 180).mean())
    idx = f.split("_")[-1].split(".")[0]
    print(f"  f{idx}: 右缘白像素占比 {white_ratio:.2f}")

# -*- coding: utf-8 -*-
"""notif/error 关键帧构图修正：整图缩小贴到大黑底画布（人物占比 100% → ~58%）
黑底图整体缩小不损人物细节，构图精确可控，避免 EditPlus 重新构图的失真
"""
import os
import numpy as np
from PIL import Image

GEN = r"F:\Zcode\桌宠\assets\gen"


def shrink(src, dst, target_ratio=0.58, bottom_margin=0.06):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    a = np.asarray(im, dtype=np.uint8)
    bright = a.max(axis=2) > 40  # 黑底人物掩码
    ys = np.where(bright.any(axis=1))[0]
    bh = ys[-1] - ys[0] + 1
    scale = target_ratio * H / bh
    nw, nh = round(W * scale), round(H * scale)
    small = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    # 人物底部落在 H*(1-bottom_margin) 处，水平居中
    x = (W - nw) // 2
    y = round(H * (1 - bottom_margin)) - nh
    canvas.paste(small, (x, y))
    canvas.save(dst)
    name = os.path.basename(src)
    print(f"{name}: bbox_h={bh}/{H} scale={scale:.2f} -> {os.path.basename(dst)} 人物占画布 {nh/H:.0%}")


shrink(rf"{GEN}\kf_notif.png", rf"{GEN}\kf_notif_v2.png")
shrink(rf"{GEN}\kf_error.png", rf"{GEN}\kf_error_v2.png")

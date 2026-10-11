# -*- coding: utf-8 -*-
"""walk 踱步镜像翻倍：正放 0..117 + 水平镜像 0..117 = 236 帧对称循环
周期 = 236/fps；fps=21 时 11.2s（换向间隔 ~5.6s），动作速度仅慢 12% 无感
两个接缝都落在"行走中→站立"的自然顿拍上（Q 版帧动画可接受）
"""
import glob, os, shutil
import numpy as np
from PIL import Image

SRC = r"F:\Zcode\桌宠\assets\sprites\luotianyi\frames-walk"
OUT = r"F:\tmp\walk-mirror"
N = 111  # 正放段帧数 0..110（114 起进入背身第二次转身，须提前截）

files = sorted(glob.glob(os.path.join(SRC, "run_*.png")))
assert len(files) >= N, f"帧数不足: {len(files)}"
seg = files[:N]

if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)

k = 0
for f in seg:  # 正放段
    Image.open(f).save(os.path.join(OUT, f"run_{k:03d}.png"))
    k += 1
for f in seg:  # 镜像段（同序水平翻转）
    a = Image.open(f)
    a.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(OUT, f"run_{k:03d}.png"))
    k += 1
print("written:", k, "frames ->", OUT)


def grid(paths, dst, cols=8, th=110):
    ims = [Image.open(p).convert("RGBA") for p in paths]
    w = max(i.width for i in ims)
    h = max(i.height for i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (w + 4), rows * (h + 4)), (255, 255, 255, 255))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * (w + 4), (i // cols) * (h + 4)), im)
    sheet.thumbnail((cols * th, rows * th))
    sheet.save(dst)
    print("grid ->", dst)


# QC 网格：全部 222 帧每 3 帧采样
allf = sorted(glob.glob(os.path.join(OUT, "run_*.png")))
grid(allf[::3], r"F:\tmp\qc-walk-mirror.png", cols=10)
# 接缝特写：接缝1 = 帧108..114(走L末)→111..117(镜像站立/起步)；接缝2 = 帧219..221(镜像走R末)→0..3(站立R)
grid(allf[105:118] + allf[216:222] + allf[0:4], r"F:\tmp\qc-walk-seam.png", cols=8)

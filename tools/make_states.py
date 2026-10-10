# -*- coding: utf-8 -*-
"""
从透明 master 立绘衍生各状态素材（第一阶段：单立绘 + 气泡/呼吸的程序化衍生）。

产出（assets/sprites/luotianyi/）：
  idle.png / idle-breathe.png   空闲呼吸双帧
  working.png                   工作中（</> 气泡，占位；正式跑步帧待 AI 生成）
  waiting.png                   等待用户确认（? 气泡）
  error.png                     出错（红 ! 气泡）
  notification.png              有通知/未读（橙 ! 气泡）
  sleeping.png                  休眠（Zzz）
  manifest.json                 状态清单
QC 拼图输出 docs/img/qc-states-dark.png。

用法：python tools/make_states.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SPR = ROOT / "assets" / "sprites" / "luotianyi"
QC = ROOT / "docs" / "img"
HEIGHT = 512
BREATHE = 1.022  # 呼吸帧竖向放大比例（底部锚定）

FONT = None
for cand in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
    try:
        FONT = ImageFont.truetype(cand, 64)
        break
    except OSError:
        pass


def bubble(img, text, color, box=(292, 16, 424, 106), font_size=56):
    """右上角圆角气泡 + 下指尾巴 + 符号。坐标基于 437x512 立绘画布。"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=26, fill=(255, 255, 255, 242),
                        outline=color + (255,), width=5)
    tx = (box[0] + box[2]) / 2
    d.polygon([(tx - 16, box[3] - 2), (tx + 16, box[3] - 2), (tx - 6, box[3] + 26)],
              fill=(255, 255, 255, 242))
    d.line([(tx - 16, box[3] - 3), (tx - 6, box[3] + 26)], fill=color + (255,), width=5)
    d.line([(tx + 16, box[3] - 3), (tx - 6, box[3] + 26)], fill=color + (255,), width=5)
    f = FONT or ImageFont.load_default(size=font_size)
    bb = d.textbbox((0, 0), text, font=f)
    d.text((tx - (bb[2] - bb[0]) / 2 - bb[0], (box[1] + box[3]) / 2 - (bb[3] - bb[1]) / 2 - bb[1]),
           text, font=f, fill=color + (255,))
    return Image.alpha_composite(img, layer)


def zzz(img):
    """右上角 Zzz（休眠）。"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    color = (128, 142, 178, 235)
    for i, (size, x, y) in enumerate([(26, 322, 100), (38, 352, 64), (50, 384, 22)]):
        f = FONT or ImageFont.load_default(size=size)
        if FONT:
            f = ImageFont.truetype(FONT.path, size)
        d.text((x, y), "Z", font=f, fill=color)
    return Image.alpha_composite(img, layer)


def breathe_frame(base):
    """竖向放大的呼吸帧，底部锚定（脚不浮空）。"""
    w, h = base.size
    nh = round(h * BREATHE)
    nw = round(w * (1 - (BREATHE - 1) * 0.6))  # 轻微收窄，体积守恒观感
    scaled = base.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, ((w - nw) // 2, h - nh))
    return canvas


def main():
    master = Image.open(SPR / "master.png").convert("RGBA")
    ratio = HEIGHT / master.height
    base = master.resize((round(master.width * ratio), HEIGHT), Image.LANCZOS)

    states = {
        "idle": base,
        "idle-breathe": breathe_frame(base),
        "working": bubble(base, "</>", (74, 116, 206)),
        "waiting": bubble(base, "?", (74, 116, 206)),
        "error": bubble(base, "!", (214, 69, 69)),
        "notification": bubble(base, "!", (232, 146, 58)),
        "sleeping": zzz(base),
    }
    for name, im in states.items():
        im.save(SPR / f"{name}.png")
        print(f"生成 {name}.png {im.size}")

    manifest = {
        "version": 1,
        "character": "luotianyi",
        "source": "素材/洛天依汉服Q版.png",
        "states": {
            "idle": {"frames": ["idle.png", "idle-breathe.png"], "fps": 0.8},
            "working": {"frames": ["working.png"], "fps": 1,
                        "note": "占位：正式版应替换为 AI 生成的多帧跑步/敲键盘动画"},
            "waiting": {"frames": ["waiting.png"], "fps": 1},
            "error": {"frames": ["error.png"], "fps": 1},
            "notification": {"frames": ["notification.png"], "fps": 1},
            "sleeping": {"frames": ["sleeping.png"], "fps": 1},
        },
        "defaults": {"scale": 0.5, "offsetY": 0, "fallbackState": "idle"},
        "stateHints": {
            "idle": "无活跃会话或全部会话静默",
            "working": "存在运行中会话（UserPromptSubmit 回合内）",
            "waiting": "PermissionRequest 等待用户确认",
            "error": "PostToolUseFailure 等失败信号（3 秒闪烁窗）",
            "notification": "Notification / 未读会话",
            "sleeping": "ZCode 客户端未运行",
        },
    }
    (SPR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("生成 manifest.json")

    # QC：深底拼图（4 列 x 2 行）
    tile, cols, rows, label_h = 300, 4, 2, 26
    names = list(states.keys())
    sheet = Image.new("RGB", (cols * tile, rows * (tile + label_h)), (32, 32, 40))
    d = ImageDraw.Draw(sheet)
    for i, name in enumerate(names):
        im = states[name].resize((tile, tile), Image.LANCZOS)
        cx, cy = (i % cols) * tile, (i // cols) * (tile + label_h)
        sheet.paste(im, (cx, cy), im)
        d.text((cx + 8, cy + tile + 5), name, fill=(220, 220, 224))
    QC.mkdir(parents=True, exist_ok=True)
    sheet.save(QC / "qc-states-dark.png")
    print("生成 docs/img/qc-states-dark.png")


if __name__ == "__main__":
    main()

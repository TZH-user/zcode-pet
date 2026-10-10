# -*- coding: utf-8 -*-
"""把生成产物整合进 assets 正式素材库并重写 manifest。

- 跑步帧序列(17帧) → assets/sprites/luotianyi/frames-working/
- celebrate / error(沮丧) / sleeping(瞌睡) 真实姿态图替换/新增
- waiting(?)/notification(!) 保留气泡占位版
用法: python tools/gen/finalize_assets.py
"""
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
SPR = ROOT / "assets" / "sprites" / "luotianyi"
GEN = ROOT / "assets" / "gen"
H = 512


def resize_save(src: Path, dst: Path):
    im = Image.open(src)
    w = round(im.width * H / im.height)
    im.resize((w, H), Image.LANCZOS).save(dst)
    print(f"{dst.relative_to(ROOT)}  {w}x{H}")


def main():
    # 跑步帧序列：统一缩放 512 高
    fdir = SPR / "frames-working"
    fdir.mkdir(exist_ok=True)
    for f in sorted((GEN / "run_frames_key").glob("run_*.png")):
        resize_save(f, fdir / f.name)

    # 姿态图
    resize_save(GEN / "lt_celebrate_alpha.png", SPR / "celebrate.png")
    (SPR / "error.png").unlink(missing_ok=True)      # 旧气泡版退役
    (SPR / "sleeping.png").unlink(missing_ok=True)
    resize_save(GEN / "lt_sad_alpha.png", SPR / "error.png")
    resize_save(GEN / "lt_sleepy_alpha.png", SPR / "sleeping.png")

    manifest = {
        "version": 2,
        "character": "luotianyi",
        "source": "素材/洛天依汉服Q版.png + 服务器 ComfyUI 生成（见 docs/03-asset-prep.md）",
        "states": {
            "idle":         {"frames": ["idle.png", "idle-breathe.png"], "fps": 0.8},
            "working":      {"dir": "frames-working", "fps": 16,
                             "note": "Animate2 姿态驱动生成，17帧原地慢跑循环"},
            "waiting":      {"frames": ["waiting.png"], "fps": 1},
            "error":        {"frames": ["error.png"], "fps": 1},
            "notification": {"frames": ["notification.png"], "fps": 1},
            "celebrate":    {"frames": ["celebrate.png"], "fps": 1,
                             "note": "会话成功完成时的庆祝态"},
            "sleeping":     {"frames": ["sleeping.png"], "fps": 1},
        },
        "defaults": {"scale": 0.5, "offsetY": 0, "fallbackState": "idle"},
        "stateHints": {
            "idle": "无活跃会话或全部会话静默",
            "working": "存在运行中会话（回合内）",
            "waiting": "PermissionRequest 等待用户确认",
            "error": "PostToolUseFailure / task_status=error",
            "notification": "tasks.unread_at 新增未读",
            "celebrate": "会话 Stop 成功终态（播放一次回落 idle）",
            "sleeping": "ZCode 客户端未运行",
        },
    }
    (SPR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("manifest.json 已更新 (v2)")


if __name__ == "__main__":
    main()

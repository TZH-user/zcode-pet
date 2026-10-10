# -*- coding: utf-8 -*-
"""批量整合：assets/gen/key_<state>/ 键控帧 → frames-<state>/ + manifest v3。

v3 变化：所有视频化状态用帧目录 {dir, fps:24}；celebrate 标记 once（单次播放）。
用法: python tools/gen/finalize_v3.py
"""
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
SPR = ROOT / "assets" / "sprites" / "luotianyi"
GEN = ROOT / "assets" / "gen"
H = 384

STATES = ["idle", "walk", "waiting", "error", "notification", "sleeping", "celebrate"]  # working 单独处理

HINTS = {
    "idle": "无活跃会话（趴枕打盹循环）",
    "walk": "1 个会话工作中（侧视踱步循环）",
    "working": "2+ 会话工作中（侧视奔跑循环）",
    "waiting": "PermissionRequest 等待确认",
    "error": "PostToolUseFailure / task_status=error（着急等待）",
    "notification": "tasks.unread_at 新增未读",
    "sleeping": "ZCode 客户端未运行（盖被深睡）",
    "celebrate": "会话成功落地，单次播放后回 idle",
}


def main():
    total = 0
    for st in STATES:
        src = GEN / f"key_{st}"
        if not src.exists():
            print(f"跳过 {st}（无 key_{st}/）")
            continue
        dst = SPR / f"frames-{st}"
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir()
        n = 0
        for f in sorted(src.glob("run_*.png")):
            im = Image.open(f)
            w = round(im.width * H / im.height)
            im.resize((w, H), Image.LANCZOS).save(dst / f.name, optimize=True)
            n += 1
        total += n
        print(f"frames-{st}/: {n} 帧")

    manifest = {
        "version": 3,
        "character": "luotianyi",
        "source": "素材/洛天依汉服Q版.png + 服务器 H3 fl2va（黑底，见 docs/04-animation-plan.md）",
        "states": {},
        "defaults": {"scale": 0.5, "offsetY": 0, "fallbackState": "idle"},
        "stateHints": HINTS,
    }
    manifest["states"]["working"] = {"dir": "frames-working", "fps": 24,
                                     "note": "H3 fl2va 正面跑（白底版，已验收）；侧视版构图漂移待重生成"}
    for st in STATES:
        d = SPR / f"frames-{st}"
        if not d.exists():
            continue
        spec = {"dir": f"frames-{st}", "fps": 24}
        if st == "celebrate":
            spec["once"] = True
        if st == "waiting":
            spec["note"] = "hooks 注册后由 PermissionRequest 触发"
        manifest["states"][st] = spec

    (SPR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manifest v3 已更新，共 {total} 帧")


if __name__ == "__main__":
    main()

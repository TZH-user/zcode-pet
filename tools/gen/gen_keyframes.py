# -*- coding: utf-8 -*-
"""六个状态的动作关键帧批量生成（pose-first 管线第一步，EditPlus 单参考）。

提示词来源: docs/04-animation-plan.md（用户已定稿管线）
用法: python tools/gen/gen_keyframes.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "素材" / "生成-2026-10-11"  # 白底原图在原始素材目录
REF = ROOT / "素材" / "洛天依汉服Q版.png"
OUT = ROOT / "assets" / "gen"

KEEP = "角色的服装款式、颜色、发型、脸型、画风与纯黑色背景（#000000，无纹理无渐变无阴影）全部保持不变，仍然是完整全身构图。"

JOBS = [
    ("kf_idle", "让画面中的Q版角色趴在一个淡蓝色圆枕上打盹：身体伏低，头枕在交叠的双臂上"
                "侧脸朝向观众，闭着眼睛表情安详，长发铺在枕头两侧，双脚翘起。枕头圆润柔软。" + KEEP),
    ("kf_wait", "让画面中的Q版角色坐在地上等待：双腿并拢侧收坐在地面，一只手托腮，另一只手"
                "搭在膝盖上，眼睛向上望，表情放空带一点期待，头顶画一个蓝色问号。" + KEEP),
    ("kf_notif", "让画面中的Q版角色好奇地张望：身体正面朝前，头微微偏向一侧，一只手举到额前"
                 "做远眺的手势，眼睛睁大，嘴巴微张，头顶画一个橙色感叹号。" + KEEP),
    ("kf_sleep", "让画面中的Q版角色侧躺在一张薄垫子上熟睡：身上盖着淡蓝色小被子只露出脑袋和"
                 "一只搭在被子边上的手，闭眼安详，头发散在垫子上，整体安静温馨。" + KEEP),
    ("kf_error", "让画面中的Q版角色焦急地等待：身体微微前倾踮着脚，双手攥拳收在胸前，眉头紧皱，"
                 "一只脚不耐烦地抬起作跺脚姿势，头顶画一个红色感叹号，额头冒一滴大大的汗珠。" + KEEP),
    ("kf_cele0", "让画面中的Q版角色屈膝半蹲蓄力准备跳起：双臂向后摆，身体微微下蹲，眼睛看向"
                 "前上方，表情兴奋期待。" + KEEP),
    ("kf_cele1", "让画面中的Q版角色跳起欢呼定格：双臂高高举过头顶张开，嘴巴大笑，眼睛弯成月牙，"
                 "身体微微离地，裙摆和发丝向上飘起。" + KEEP),
]

script = Path(__file__).parent / "submit_editplus.py"

for name, prompt in JOBS:
    print(f"===== {name} =====", flush=True)
    cmd = [sys.executable, str(script), "--ref", str(REF), "--prompt", prompt,
           "--res", "1024x1200", "--port", "8188",
           "--prefix", name, "--out", str(OUT)]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"!! {name} 失败 rc={r.returncode}", flush=True)

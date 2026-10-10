# -*- coding: utf-8 -*-
"""洛天依桌宠姿态变体生成（EditPlus 单参考图编辑，Qwen-Image-2.1）。

用法: python tools/gen/gen_poses.py
提交 3 个姿态编辑任务并下载到 assets/gen/。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "assets" / "gen" / "lt_white_input.png"
OUT = ROOT / "assets" / "gen"

JOBS = [
    ("celebrate", "让画面中的Q版角色开心地欢呼庆祝：双臂高高举过头顶张开，嘴巴大笑，"
                  "眼睛弯成月牙，身体微微跳起离地，裙摆和发丝随动作飘起。"
                  "角色的服装款式、颜色、发型、脸型、画风、线条与纯白背景全部保持不变，"
                  "仍然是完整的全身立绘构图。"),
    ("sad", "让画面中的Q版角色变得沮丧委屈：头微微低下，肩膀下垂，双臂无力地垂在身体两侧，"
            "嘴角向下撇，眉毛呈八字愁眉，头顶冒出一滴大大的汗珠。"
            "角色的服装款式、颜色、发型、脸型、画风、线条与纯白背景全部保持不变，"
            "仍然是完整的全身立绘构图。"),
    ("sleepy", "让画面中的Q版角色闭着眼睛打瞌睡：头微微歪向一侧，双手合十贴在脸颊旁边，"
               "表情安详，头顶画三个蓝色的小Z字母，身体轻轻摇晃的姿态。"
               "角色的服装款式、颜色、发型、脸型、画风、线条与纯白背景全部保持不变，"
               "仍然是完整的全身立绘构图。"),
]

script = Path(__file__).parent / "submit_editplus.py"

for name, prompt in JOBS:
    print(f"\n===== {name} =====")
    cmd = [sys.executable, str(script),
           "--ref", str(REF), "--prompt", prompt,
           "--res", "1024x1200", "--port", "8188",
           "--prefix", f"lt_{name}", "--out", str(OUT)]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"!! {name} 失败 rc={r.returncode}")

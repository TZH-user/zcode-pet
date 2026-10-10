# -*- coding: utf-8 -*-
"""8 状态视频批量键控：h3_<state>.mp4 → key_<state>/（黑底亮度键+接缝混合）。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GEN = ROOT / "assets" / "gen"
# (最终状态目录名, 批量产物文件名)——gen_h3_batch 用短名 wait/notif/sleep
STATES = [("idle", "idle"), ("walk", "walk"), ("working", "working"),
          ("waiting", "wait"), ("error", "error"), ("notification", "notif"),
          ("sleeping", "sleep"), ("celebrate", "celebrate")]

for st, fkey in STATES:
    # 强制重键控
    mp4 = GEN / f"h3_{fkey}.mp4"
    src = GEN / f"src_{st}"
    if src.exists():
        subprocess.run(["rm", "-rf", str(src)], check=False)
    src.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), str(src / "f_%04d.png")], check=True)
    seam = "0" if st == "celebrate" else "3"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen" / "key_frames.py"),
                        str(src), str(GEN / f"key_{st}"),
                        "--tol", "30", "--sat", "30", "--smooth", "0",
                        "--seamblend", seam, "--bg", "black", "--trim-last", "2"],
                       capture_output=True, text=True)
    tail = (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "?"
    print(f"{st}: {tail}", flush=True)

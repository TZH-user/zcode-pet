# -*- coding: utf-8 -*-
"""v3 三状态链路：h3_{walk3,notif2,error2}.mp4 → 键控 → [walk 镜像翻倍] → frames-* + manifest
用法: python tools/gen/chain_v3.py [walk|notif|error ...] [--mirror N]
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
GEN = ROOT / "assets" / "gen"
SPR = ROOT / "assets" / "sprites" / "luotianyi"
H = 384

JOBS = {"walk": "walk4", "notif": "notif2", "error": "error2"}


def key_video(fkey, out_key):
    src = GEN / f"src_v3_{fkey}"
    if src.exists():
        shutil.rmtree(src)
    src.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(GEN / f"h3_{fkey}.mp4"),
                    str(src / "f_%04d.png")], check=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "gen" / "key_frames.py"),
                    str(src), str(GEN / out_key),
                    "--tol", "30", "--sat", "30", "--smooth", "0",
                    "--seamblend", "3", "--bg", "black", "--trim-last", "2"], check=True)


def find_mirror_n(key_dir):
    """自动定位镜像点：朝左走稳定段末端 = 宽度膨胀(二次转身)起点前一帧"""
    files = sorted((GEN / key_dir).glob("run_*.png"))
    ws = []
    for f in files:
        a = np.asarray(Image.open(f).convert("RGBA"))
        m = a[..., 3] > 128
        xs = np.where(m.any(axis=0))[0]
        ws.append(xs[-1] - xs[0] + 1 if len(xs) else 0)
    ws = np.array(ws)
    med = np.median(ws)
    spike = np.where(ws > med * 1.12)[0]  # 转身裙摆展开
    # 只找视频后半段的第一次膨胀（第二次转身起点）
    half = len(ws) // 2
    late = spike[spike > half]
    n = int(late[0] - 3) if len(late) else len(ws) - 6
    return files, max(60, min(n, len(ws) - 6))


def mirror_double(key_dir, out_key, n):
    files = sorted((GEN / key_dir).glob("run_*.png"))
    out = GEN / out_key
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    k = 0
    for f in files[:n]:
        Image.open(f).save(out / f"run_{k:03d}.png"); k += 1
    for f in files[:n]:
        Image.open(f).transpose(Image.FLIP_LEFT_RIGHT).save(out / f"run_{k:03d}.png"); k += 1
    return k


def finalize(key_dir, frame_dir, state, fps, note):
    src = GEN / key_dir
    dst = SPR / frame_dir
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir()
    for f in sorted(src.glob("run_*.png")):
        im = Image.open(f)
        im.resize((round(im.width * H / im.height), H), Image.LANCZOS).save(
            dst / f.name, optimize=True)
    mf = SPR / "manifest.json"
    m = json.loads(mf.read_text(encoding="utf-8"))
    m["states"][state] = {"dir": frame_dir, "fps": fps, "note": note}
    mf.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    which = sys.argv[1:] or list(JOBS)
    mirror_n = None
    if "--mirror" in which:
        i = which.index("--mirror")
        mirror_n = int(which[i + 1])
        which = [w for j, w in enumerate(which) if j not in (i, i + 1)]

    for w in which:
        fkey = JOBS[w]
        print(f"== {w}: 键控 {fkey}", flush=True)
        key_video(fkey, f"key_v3_{w}")

    if "walk" in which:
        files, n_auto = find_mirror_n("key_v3_walk")
        n = mirror_n or n_auto
        total = mirror_double("key_v3_walk", "key_v3_walkfinal", n)
        print(f"== walk: 镜像点 {n}（自动建议），翻倍后 {total} 帧 @20fps = {total/20:.1f}s", flush=True)
        finalize("key_v3_walkfinal", "frames-walk", "walk", 20, "fl2va 大步幅往返+镜像翻倍")
    if "notif" in which:
        finalize("key_v3_notif", "frames-notification", "notification", 24,
                 "fl2va 全身远景重新生成（修近景构图）")
        print("== notif 完成", flush=True)
    if "error" in which:
        finalize("key_v3_error", "frames-error", "error", 24,
                 "fl2va 全身远景重新生成（修近景构图）")
        print("== error 完成", flush=True)


if __name__ == "__main__":
    main()

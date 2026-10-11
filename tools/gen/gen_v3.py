# -*- coding: utf-8 -*-
"""v3 批量生成：walk3(大步幅往返) / notif2(全身远景) / error2(全身远景)
走 fl2va bridge :8001（fl2va2 容器，vLLM 占用 8000 后的避让端口）
"""
import json
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ssh_put  # noqa: E402

GEN = Path(__file__).resolve().parent.parent.parent / "assets" / "gen"
BASE = "http://192.168.20.20:8001"
HOST_SHARED = "/workspace/models-moved/minimax-h3/_comfy_input/bridge"
CONT_SHARED = "/models/minimax-h3/_comfy_input/bridge"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

NOGHOST = ("人物轮廓边缘干净锐利，无运动残影，无重影，无半透明拖尾，纯黑色背景，"
           "赛璐璐动画风格，首尾姿态完全一致，固定镜头")
FAR = ("人物完整全身入镜，占画面高度约三分之二，头顶和脚下都留有黑色空间，"
       "人物全身始终完整在画面中不放大不推近，")

JOBS = {
    "walk3": {
        "kf": "kf_walkstride_raw.png",
        "frames": 17 * 9 + 5,
        "prompt": ("完整侧面视角，Q版少女原地往返踱步：先向画面右侧行走几步，每一步都大幅"
                   "跨出、迈步距离很大，双腿大幅度交替，身体随步伐明显向行进方向移动，停下后"
                   "原地转身面向画面左侧，再迈大步向左行走几步回到起点位置，然后再次转身，"
                   "行走动作连贯自然循环，身体侧对镜头，头部自然朝向行进方向，不看向镜头，"
                   "步伐轻快有力，裙摆随步伐大幅摆动，" + NOGHOST),
        "seed": "864209",
    },
    "notif2": {
        "kf": "kf_notif_v2.png",
        "frames": 17 * 6 + 5,
        "prompt": ("Q版少女全身远景循环动画，" + FAR +
                   "好奇地左右张望，头部轻轻左右转动，眼睛偶尔眨动，踮起的脚跟微微上下，"
                   "头顶橙色感叹号轻轻摇摆，动作轻柔连贯循环，" + NOGHOST),
        "seed": "41001",
    },
    "error2": {
        "kf": "kf_error_v2.png",
        "frames": 17 * 6 + 5,
        "prompt": ("Q版少女全身远景循环动画，" + FAR +
                   "着急等待原地小碎步跺脚，双手握拳收在胸前，身体微微前倾左右张望，头顶"
                   "红色感叹号轻轻跳动，表情着急但可爱，动作轻柔连贯循环，" + NOGHOST),
        "seed": "41002",
    },
    "walk4": {
        "kf": "kf_walkside.png",   # 自然走姿关键帧（v2 原版，动作自然；v3 极端跨步导致劈叉感）
        "frames": 17 * 9 + 5,
        "prompt": ("完整侧面视角，Q版少女原地往返踱步：先向画面右侧行走几步，步伐自然迈开，"
                   "双腿交替协调流畅，重心平稳，身体随步伐轻微起伏，动作放松自然像散步，停下后"
                   "原地转身面向画面左侧，再自然地向左行走几步回到起点位置，然后再次转身，行走"
                   "动作连贯自然循环，身体侧对镜头，头部自然朝向行进方向，不看向镜头，裙摆随步伐"
                   "轻柔摆动，" + NOGHOST),
        "seed": "55021",
    },
}


def multipart(fields):
    b = "----wkv3" + uuid.uuid4().hex[:6]
    body = b""
    for k, v in fields.items():
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def run_job(name, job):
    tag = f"[{name}]"
    for i in (0, 1):
        n = ssh_put.put(str(GEN / job["kf"]), f"{HOST_SHARED}/b_{name}_{i}.png")
        print(f"{tag} 上传 {n}B", flush=True)
    data = {"task": "fl2va", "prompt": job["prompt"],
            "target": json.dumps({"short_edge": 768, "aspect_ratio": "1:1",
                                  "duration_seconds": round(job["frames"] / 24, 6)}),
            "num_inference_steps": "30", "seed": job["seed"],
            "conditions": json.dumps([
                {"type": "image", "role": "keyframe", "uri": f"{CONT_SHARED}/b_{name}_0.png", "frame_index": 0},
                {"type": "image", "role": "keyframe", "uri": f"{CONT_SHARED}/b_{name}_1.png", "frame_index": -1}])}
    body, ctype = multipart(data)
    try:
        j = json.loads(opener.open(urllib.request.Request(
            BASE + "/v1/videos", data=body, headers={"Content-Type": ctype}), timeout=300).read().decode())
    except urllib.error.HTTPError as e:
        print(f"{tag} 被拒: {e.read().decode(errors='ignore')[:300]}", flush=True)
        return
    vid = j["id"]
    print(f"{tag} 受理 {vid[:8]} frames={job['frames']}", flush=True)
    t0 = time.time()
    while time.time() - t0 < 3600:
        time.sleep(20)
        try:
            st = json.loads(opener.open(f"{BASE}/v1/videos/{vid}", timeout=30).read().decode())
        except Exception as e:
            print(f"{tag} 轮询异常 {e}", flush=True); continue
        s = st.get("status")
        print(f"{tag} [{time.time()-t0:.0f}s] {s}", flush=True)
        if s == "completed":
            break
        if s == "failed":
            print(f"{tag} 失败: {str(st.get('error'))[:300]}", flush=True)
            return
    dst = GEN / f"h3_{name}.mp4"
    with opener.open(f"{BASE}/v1/videos/{vid}/content", timeout=900) as r, open(dst, "wb") as f:
        f.write(r.read())
    print(f"{tag} 已下载 {dst} {dst.stat().st_size/1e6:.1f}MB", flush=True)


if __name__ == "__main__":
    names = sys.argv[1:] or list(JOBS)
    threads = [threading.Thread(target=run_job, args=(n, JOBS[n])) for n in names]
    for t in threads: t.start()
    for t in threads: t.join()
    print("ALL DONE", flush=True)

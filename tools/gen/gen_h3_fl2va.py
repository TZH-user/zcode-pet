# -*- coding: utf-8 -*-
"""MiniMax-H3 fl2va（首尾帧→视频）提交客户端，直连服务器 SGLang :8000。

API 契约（源自 custom_nodes/comfyui_h3_sglang_bridge/__init__.py，勿凭记忆改）：
  POST /v1/videos  multipart/form-data:
    task=fl2va, prompt, target=JSON{short_edge,aspect_ratio,duration_seconds},
    num_inference_steps, seed, conditions=JSON[{type:image,role:keyframe,
    uri:<容器路径>, frame_index:0|-1}]
  禁止 negative_prompt / guidance_scale / num_frames / fps（CFG 蒸馏）。
  fps 恒 24，帧数 17n+5；轮询 GET /v1/videos/{id}；下载 GET .../content。

用法:
  python tools/gen/gen_h3_fl2va.py run  # 首帧=末帧=关键帧，提交并下载
"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://192.168.20.20:8000"
HOST_SHARED = "/home/sqls/models/minimax-h3/_comfy_input/bridge"
CONTAINER_SHARED = "/models/minimax-h3/_comfy_input/bridge"
FPS = 24
STEPS = 30
DURATION_S = 4.0          # 最短 4.0 → 107 帧
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def multipart(fields: dict) -> tuple[bytes, str]:
    b = "----h3fl2va" + uuid.uuid4().hex[:8]
    body = b""
    for k, v in fields.items():
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    body += f"--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode != "run":
        print(__doc__)
        return

    kf0, kf1 = "kf0_ltpet.png", "kf1_ltpet.png"   # 由 SSH 预先放入共享目录
    frames = 17 * 6 + 5                            # 最短时长 4.0s → 107 帧（17n+5）
    conditions = [
        {"type": "image", "role": "keyframe", "uri": f"{CONTAINER_SHARED}/{kf0}", "frame_index": 0},
        {"type": "image", "role": "keyframe", "uri": f"{CONTAINER_SHARED}/{kf1}", "frame_index": -1},
    ]
    data = {
        "task": "fl2va",
        "prompt": "Q版二次元少女全身原地小幅度轻快跑步循环动画，蓝白色汉服裙装，银白色长发双马尾配蓝色花饰，"
                  "正对镜头原地小碎步跑步，摆幅小而轻快，裙摆和长发只有轻微摆动，"
                  "人物轮廓边缘干净锐利，无运动残影，无重影，无半透明拖尾，无模糊，"
                  "纯白色背景，赛璐璐动画风格，线条清晰，首尾姿态完全一致，固定镜头",
        "target": json.dumps({"short_edge": 768, "aspect_ratio": "1:1",
                              "duration_seconds": round(frames / FPS, 6)}),
        "num_inference_steps": str(STEPS),
        "seed": "77071",
        "conditions": json.dumps(conditions),
    }
    body, ctype = multipart(data)
    req = urllib.request.Request(BASE + "/v1/videos", data=body,
                                 headers={"Content-Type": ctype})
    try:
        job = json.loads(opener.open(req, timeout=120).read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"提交被拒({e.code}): {e.read().decode(errors='ignore')[:800]}")
    vid = job["id"]
    print(f"已受理 id={vid} status={job.get('status')} frames≈{frames}")

    t0 = time.time()
    while True:
        time.sleep(15)
        try:
            st = json.loads(opener.open(f"{BASE}/v1/videos/{vid}", timeout=30).read().decode())
        except Exception as e:
            print(f"  轮询暂失败 {e}")
            continue
        s = st.get("status")
        print(f"  [{time.time()-t0:.0f}s] {s} progress={st.get('progress')}%")
        if s == "completed":
            print(f"  推理 {st.get('inference_time_s')}s 峰值显存 {st.get('peak_memory_mb')}MB")
            break
        if s == "failed":
            raise SystemExit("生成失败: " + json.dumps(st.get("error"), ensure_ascii=False)[:600])
        if time.time() - t0 > 1800:
            raise SystemExit(f"超时 id={vid}")

    out = Path(__file__).resolve().parent.parent.parent / "assets" / "gen"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / "lt_run_h3.mp4"
    with opener.open(f"{BASE}/v1/videos/{vid}/content", timeout=600) as r, open(dst, "wb") as f:
        f.write(r.read())
    print(f"已下载 {dst} {dst.stat().st_size/1e6:.1f}MB")


if __name__ == "__main__":
    main()

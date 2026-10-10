# -*- coding: utf-8 -*-
"""working 侧视重试：紧构图关键帧（黑底垫满）单任务提交。"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ssh_put  # noqa: E402

GEN = Path(__file__).resolve().parent.parent.parent / "assets" / "gen"
BASE = "http://192.168.20.20:8000"
HOST_SHARED = "/workspace/models-moved/minimax-h3/_comfy_input/bridge"
CONT_SHARED = "/models/minimax-h3/_comfy_input/bridge"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PROMPT = ("完整侧面视角，Q版少女面朝画面右侧原地奔跑，身体完全侧对镜头，头部自然朝向前进"
          "方向目视前方，绝不转头看向镜头，构图固定角色大小不变，双腿大幅交替奔跑，双臂前后"
          "摆动，裙摆和长发向后飘动，人物轮廓边缘干净锐利，无运动残影，无重影，无半透明拖尾，"
          "纯黑色背景，赛璐璐动画风格，首尾姿态完全一致，固定镜头")


def multipart(fields):
    b = "----w2" + uuid.uuid4().hex[:6]
    body = b""
    for k, v in fields.items():
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def main():
    for i in (0, 1):
        n = ssh_put.put(str(GEN / "kf_runside_tight.png"), f"{HOST_SHARED}/b_work2_{i}.png")
        print(f"上传 {n}B", flush=True)
    frames = 107
    data = {"task": "fl2va", "prompt": PROMPT,
            "target": json.dumps({"short_edge": 768, "aspect_ratio": "1:1",
                                  "duration_seconds": round(frames / 24, 6)}),
            "num_inference_steps": "30", "seed": "552210",
            "conditions": json.dumps([
                {"type": "image", "role": "keyframe", "uri": f"{CONT_SHARED}/b_work2_0.png", "frame_index": 0},
                {"type": "image", "role": "keyframe", "uri": f"{CONT_SHARED}/b_work2_1.png", "frame_index": -1}])}
    body, ctype = multipart(data)
    try:
        job = json.loads(opener.open(urllib.request.Request(
            BASE + "/v1/videos", data=body, headers={"Content-Type": ctype}), timeout=60).read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"被拒: {e.read().decode(errors='ignore')[:400]}")
    vid = job["id"]
    print("受理", vid[:8], flush=True)
    t0 = time.time()
    while time.time() - t0 < 1500:
        time.sleep(15)
        st = json.loads(opener.open(f"{BASE}/v1/videos/{vid}", timeout=30).read().decode())
        s = st.get("status")
        print(f"  [{time.time()-t0:.0f}s] {s}", flush=True)
        if s == "completed":
            break
        if s == "failed":
            raise SystemExit("失败: " + str(st.get("error"))[:300])
    dst = GEN / "h3_work2.mp4"
    with opener.open(f"{BASE}/v1/videos/{vid}/content", timeout=600) as r, open(dst, "wb") as f:
        f.write(r.read())
    print(f"已下载 {dst} {dst.stat().st_size/1e6:.1f}MB", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""六状态 fl2va 批量生成：上传关键帧 → 提交 → 轮询全部完成 → 下载。

前置：SGLang fl2va 容器运行中（qwen38-h3-fl2va）。
关键帧: assets/gen/kf_*.png（EditPlus 产物）+ celebrate.png（末帧）
用法: python tools/gen/gen_h3_batch.py
"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ssh_put  # noqa: E402  复用其 ssh_exec 通道

from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
GEN = ROOT / "assets" / "gen"
SPR = ROOT / "assets" / "sprites" / "luotianyi"
BASE = "http://192.168.20.20:8000"
HOST_SHARED = "/workspace/models-moved/minimax-h3/_comfy_input/bridge"
CONT_SHARED = "/models/minimax-h3/_comfy_input/bridge"
FPS = 24
STEPS = 30
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

NOGHOST = ("人物轮廓边缘干净锐利，无运动残影，无重影，无半透明拖尾，"
           "纯白色背景，赛璐璐动画风格，首尾姿态完全一致，固定镜头")

JOBS = {
    "idle": ("Q版少女趴在淡蓝色圆枕上打盹的循环动画，身体随呼吸轻微起伏，长发发梢微微飘动，"
             "双脚偶尔轻晃，闭眼安详，" + NOGHOST, "kf_idle.png", "kf_idle.png"),
    "wait": ("Q版少女坐在地上托腮等待的循环动画，托腮的手指轻点脸颊，双眼偶尔眨动，双脚脚尖"
             "上下轻晃，头顶问号轻轻摇摆，" + NOGHOST, "kf_wait.png", "kf_wait.png"),
    "error": ("Q版少女焦急等待的循环动画，原地小碎步急促踱步，身体微微前倾左右张望，攥拳的"
              "双手小幅摆动，跺脚，头顶红色感叹号微微抖动，" + NOGHOST, "kf_error.png", "kf_error.png"),
    "notif": ("Q版少女好奇张望的循环动画，头部左右轻轻转动张望，眼睛偶尔眨动，踮起的脚跟微微"
              "上下，头顶感叹号轻轻摇摆，" + NOGHOST, "kf_notif.png", "kf_notif.png"),
    "sleep": ("Q版少女盖着小被子侧躺熟睡的循环动画，被子随呼吸轻微起伏，偶尔咂一下嘴，发丝极"
              "轻微地动，" + NOGHOST, "kf_sleep.png", "kf_sleep.png"),
    "celebrate": ("Q版少女原地跳起欢呼：从屈膝蓄力向上跃起，双臂从身后向前上方挥举过头顶，裙摆"
                  "随跳跃扬起，落回地面双臂保持高举定格，表情大笑，人物轮廓边缘干净锐利，无运动"
                  "残影，无重影，纯白色背景，赛璐璐动画风格，固定镜头",
                  "kf_cele0.png", "celebrate.png"),
    "working": ("完整侧面视角，Q版少女面朝画面右侧原地奔跑，身体完全侧对镜头，头部自然朝向前进"
                "方向目视前方，绝不转头看向镜头，双腿大幅交替奔跑，双臂前后摆动，裙摆和长发向后"
                "飘动，" + NOGHOST, "kf_runside.png", "kf_runside.png"),
    "walk": ("完整侧面视角，Q版少女面朝画面右侧在原地小范围来回踱步：向右走几步后自然转身向左"
             "走回起点，身体侧对镜头，头部自然朝向行进方向，不看向镜头，步伐悠闲，裙摆轻摆，"
             + NOGHOST, "kf_walkside.png", "kf_walkside.png"),
}


def pad_square(src: Path, dst: Path, side=768):
    im = Image.open(src).convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    s = max(bg.size)
    sq = Image.new("RGB", (s, s), (255, 255, 255))
    sq.paste(bg, ((s - bg.width) // 2, (s - bg.height) // 2))
    sq.resize((side, side), Image.LANCZOS).save(dst)


def multipart(fields: dict):
    b = "----h3batch" + uuid.uuid4().hex[:8]
    body = b""
    for k, v in fields.items():
        body += (f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def main():
    frames = 17 * 6 + 5
    ids = {}
    for state, (prompt, kf0, kf1) in JOBS.items():
        up = []
        for i, src_name in enumerate((kf0, kf1)):
            src = GEN / src_name if src_name.startswith("kf_") else SPR / src_name
            tmp = GEN / f"_sq_{state}_{i}.png"
            pad_square(src, tmp)
            remote = f"{HOST_SHARED}/b_{state}_{i}.png"
            n = ssh_put.put(str(tmp), remote)
            print(f"  上传 {state}[{i}] {n}B", flush=True)
            up.append(f"{CONT_SHARED}/b_{state}_{i}.png")
        conditions = [
            {"type": "image", "role": "keyframe", "uri": up[0], "frame_index": 0},
            {"type": "image", "role": "keyframe", "uri": up[1], "frame_index": -1},
        ]
        data = {"task": "fl2va", "prompt": prompt,
                "target": json.dumps({"short_edge": 768, "aspect_ratio": "1:1",
                                      "duration_seconds": round(frames / FPS, 6)}),
                "num_inference_steps": str(STEPS), "seed": str(abs(hash(state)) % 10**8),
                "conditions": json.dumps(conditions)}
        body, ctype = multipart(data)
        req = urllib.request.Request(BASE + "/v1/videos", data=body, headers={"Content-Type": ctype})
        try:
            job = json.loads(opener.open(req, timeout=120).read().decode())
            ids[state] = job["id"]
            print(f"{state} 受理 {job['id'][:8]}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"{state} 提交被拒: {e.read().decode(errors='ignore')[:300]}", flush=True)

    print(f"共提交 {len(ids)} 个任务，开始轮询…", flush=True)
    done = {}
    t0 = time.time()
    while len(done) < len(ids) and time.time() - t0 < 5400:
        time.sleep(20)
        for state, vid in list(ids.items()):
            if state in done:
                continue
            try:
                st = json.loads(opener.open(f"{BASE}/v1/videos/{vid}", timeout=30).read().decode())
            except Exception:
                continue
            s = st.get("status")
            if s == "completed":
                done[state] = vid
                print(f"  {state} 完成（累计{len(done)}/{len(ids)}）", flush=True)
            elif s == "failed":
                print(f"  {state} 失败: {json.dumps(st.get('error'), ensure_ascii=False)[:200]}", flush=True)
                done[state] = vid + "|FAILED"
    for state, vid in done.items():
        if vid.endswith("|FAILED"):
            continue
        dst = GEN / f"h3_{state}.mp4"
        with opener.open(f"{BASE}/v1/videos/{vid}/content", timeout=600) as r, open(dst, "wb") as f:
            f.write(r.read())
        print(f"已下载 {dst.name} {dst.stat().st_size/1e6:.1f}MB", flush=True)


if __name__ == "__main__":
    main()

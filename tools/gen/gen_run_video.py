# -*- coding: utf-8 -*-
"""Animate2 跑步帧生成：旧 jog 视频提骨架 → 换装洛天依（汉服）动画。

子命令:
  upload    上传参考图（垫方白底）与动作源视频到服务器 input/
  skeleton  提交骨架提取 QC 任务并下载骨架帧
  animate   提交 WanAnimate2ToVideo 正式生成并下载 mp4
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
GEN = ROOT / "assets" / "gen"
REF_SRC = GEN / "lt_white_input.png"
POSE_SRC = Path(r"F:\本地部署\05_日志\pet-loop-test\jog-a-cut.mp4")
OUT = GEN

BASE = "http://192.168.20.20:8188"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

LENGTH = 17          # 4n+1，与源视频帧数一致
SIZE = 640           # 方形输出，与源视频 768x768 同比例
STEPS = 20


def get(url, timeout=20):
    return opener.open(url, timeout=timeout).read().decode()


def upload(path, ctype):
    data = Path(path).read_bytes()
    b = "----ltpet"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{Path(path).name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode() \
        + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(BASE + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return json.loads(opener.open(req, timeout=300).read().decode())["name"]


def prepare_ref():
    """参考图垫成方形白底并缩到 1024，返回本地路径。"""
    im = Image.open(REF_SRC)
    side = max(im.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    canvas = canvas.resize((1024, 1024), Image.LANCZOS)
    p = GEN / "lt_square_ref.png"
    canvas.save(p)
    return p


def submit(wf, poll=6, max_wait=3600):
    try:
        pid = json.loads(opener.open(urllib.request.Request(
            BASE + "/prompt", data=json.dumps({"prompt": wf}).encode(),
            headers={"Content-Type": "application/json"}), timeout=60).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"提交被拒({e.code}): {e.read().decode(errors='ignore')[:1200]}")
    print("prompt_id:", pid)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll)
        try:
            h = json.loads(get(f"{BASE}/history/{pid}"))
        except Exception:
            continue
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed") or st.get("status_str") == "error":
                return pid, h[pid]
            print(f"  [{time.time()-t0:.0f}s] status={st.get('status_str')}")
    raise TimeoutError(pid)


def fetch(hist, out_dir, stem):
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for key in ("images", "videos", "gifs"):
            for im in node_out.get(key, []):
                if im.get("type") != "output":
                    continue
                q = f"/view?filename={im['filename']}&subfolder={im.get('subfolder','')}&type={im['type']}"
                ext = Path(im["filename"]).suffix or ".mp4"
                # 保留服务器侧去重序号（SaveImage 同前缀会输出 _00001_ 尾缀）
                tail = Path(im["filename"]).stem.replace(stem, "").replace("-", "_")
                dst = out_dir / f"{stem}{tail}{ext}"
                with opener.open(BASE + q, timeout=300) as r, open(dst, "wb") as f:
                    f.write(r.read())
                saved.append(dst)
    return saved


def check_error(pid, hist):
    st = hist.get("status", {})
    if st.get("status_str") == "error":
        for m in st.get("messages", []):
            if m[0] == "execution_error":
                raise SystemExit(f"执行失败 {pid}: {m[1].get('node_type')} -> {m[1].get('exception_message')[:400]}")
        raise SystemExit(f"执行失败 {pid}")


def wf_skeleton(ref, pose_video):
    return {
        "9":  {"class_type": "LoadVideo", "inputs": {"file": pose_video}},
        "10": {"class_type": "GetVideoComponents", "inputs": {"video": ["9", 0]}},
        "11": {"class_type": "ImageFromBatch", "inputs": {"image": ["10", 0], "batch_index": 0, "length": LENGTH}},
        "19": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdpose_wholebody_fp16.safetensors"}},
        "20": {"class_type": "SDPoseKeypointExtractor", "inputs": {"model": ["19", 0], "vae": ["19", 2], "image": ["11", 0], "batch_size": 16}},
        "21": {"class_type": "SDPoseDrawKeypoints", "inputs": {"keypoints": ["20", 0], "draw_body": True, "draw_hands": True,
                                                               "draw_face": True, "draw_feet": False, "stick_width": 4,
                                                               "face_point_size": 3, "score_threshold": 0.3, "draw_head": True}},
        "22": {"class_type": "SaveImage", "inputs": {"images": ["21", 0], "filename_prefix": "lt_skeleton"}},
    }


def wf_animate(ref, pose_video, seed=20261010):
    return {
        "1":  {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_animate_14B_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2":  {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "3":  {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "4":  {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "clip_vision_h.safetensors"}},
        "5":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text":
               "Q版二次元少女全身立绘原地慢跑动画，蓝白色汉服裙装，银白色长发双马尾配蓝花发饰，"
               "正对镜头原地跑步，双臂自然前后摆动，裙摆和长发随动作飘动，"
               "纯白色背景，赛璐璐动画风格，线条干净，动作平滑循环，固定镜头"}},
        "6":  {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text":
               "写实风格, 摄影照片, 3D渲染, 真人质感, 多人, 肢体扭曲, 多余的手指, 面部崩坏, "
               "复杂背景, 阴影地面, 文字, 水印, 字幕, 镜头运动"}},
        "7":  {"class_type": "LoadImage", "inputs": {"image": ref}},
        "8":  {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["4", 0], "image": ["7", 0], "crop": "center"}},
        "9":  {"class_type": "LoadVideo", "inputs": {"file": pose_video}},
        "10": {"class_type": "GetVideoComponents", "inputs": {"video": ["9", 0]}},
        "11": {"class_type": "ImageFromBatch", "inputs": {"image": ["10", 0], "batch_index": 0, "length": LENGTH}},
        "19": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdpose_wholebody_fp16.safetensors"}},
        "20": {"class_type": "SDPoseKeypointExtractor", "inputs": {"model": ["19", 0], "vae": ["19", 2], "image": ["11", 0], "batch_size": 16}},
        "21": {"class_type": "SDPoseDrawKeypoints", "inputs": {"keypoints": ["20", 0], "draw_body": True, "draw_hands": True,
                                                               "draw_face": True, "draw_feet": False, "stick_width": 4,
                                                               "face_point_size": 3, "score_threshold": 0.3, "draw_head": True}},
        "12": {"class_type": "WanAnimate2ToVideo", "inputs": {
               "positive": ["5", 0], "negative": ["6", 0], "vae": ["3", 0],
               "width": SIZE, "height": SIZE, "length": LENGTH, "batch_size": 1,
               "video_frame_offset": 0, "pose_strength": 1.0,
               "pose_start_percent": 0.0, "pose_end_percent": 1.0,
               "reference_image_strength": 1.0,
               "reference_image": ["7", 0], "pose_video": ["21", 0], "clip_vision_output": ["8", 0]}},
        "13": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": seed, "steps": STEPS, "cfg": 6.0,
               "sampler_name": "uni_pc", "scheduler": "simple",
               "positive": ["12", 0], "negative": ["12", 1], "latent_image": ["12", 2], "denoise": 1.0}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}},
        "15": {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "fps": 16}},
        "16": {"class_type": "SaveVideo", "inputs": {"video": ["15", 0], "filename_prefix": "lt_run", "format": "mp4"}},
    }


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "upload":
        ref = prepare_ref()
        print("ref upload:", upload(ref, "image/png"))
        print("pose upload:", upload(POSE_SRC, "video/mp4"))
    elif cmd == "skeleton":
        pid, hist = submit(wf_skeleton("lt_square_ref.png", "jog-a-cut.mp4"), max_wait=1800)
        check_error(pid, hist)
        print("saved:", [str(p) for p in fetch(hist, OUT, "skeleton_sheet")])
    elif cmd == "animate":
        pid, hist = submit(wf_animate("lt_square_ref.png", "jog-a-cut.mp4"))
        check_error(pid, hist)
        print("saved:", [str(p) for p in fetch(hist, OUT, "lt_run_hanfu")])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

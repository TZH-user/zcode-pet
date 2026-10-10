# -*- coding: utf-8 -*-
"""EditPlus 工作流参数化提交：输出分辨率可选

分辨率三种给法（都不给 = 保持 JSON 里写死的 1216x832）:
  --preset portrait|landscape|square|hd|hd-portrait
  --res 832x1216
  --width 1824 --height 1216
宽高会自动对齐到 16 的倍数（Qwen VAE 8x 下采样 x patch 2）。

其他可选: --ref 参考图 / --prompt 编辑指令 / --seed / --prefix / --out / --host / --port
不传 --ref 时用 JSON 里写死的图（需已存在于服务器 input）。

用法示例:
  python submit_editplus.py --ref canon.png --prompt "..." --preset portrait
  python submit_editplus.py --ref canon.png --prompt "..." --res 1824x1216
  python submit_editplus.py --ref canon.png --prompt "..." --width 1472 --height 1136 --out renders
"""
import argparse, json, os, random, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WF_PATH = os.path.join(HERE, "qwen_image_editplus_api.json")
DEFAULT_HOST = "192.168.20.20"
PORTS = [8188, 8189]

# 尺寸来源：EditPlus编辑模式说明.md 中 13 类资产实际用到的档位
PRESETS = {
    "portrait":    (832, 1216),   # 竖版全身 / 服饰平铺
    "landscape":   (1216, 832),   # 横版三视图
    "square":      (1024, 1024),  # 局部特写 / 表情
    "hd":          (1824, 1216),  # 高清横版
    "hd-portrait": (1216, 1824),  # 高清竖版
}

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, timeout=15):
    return opener.open(url, timeout=timeout).read().decode()


def pick_host(host, port):
    """指定 port 直接用；否则在 8188/8189 里挑显存空闲最大的"""
    if port:
        return f"http://{host}:{port}"
    best = None
    for p in PORTS:
        base = f"http://{host}:{p}"
        try:
            st = json.loads(get(base + "/system_stats"))
            gpu = st["devices"][0]
            print(f"{base}  显存空闲 {gpu['vram_free']/1e9:.1f}G / {gpu['vram_total']/1e9:.1f}G")
            if best is None or gpu["vram_free"] > best[1]:
                best = (base, gpu["vram_free"])
        except Exception as e:
            print(f"{base} 不可用: {e}")
    if not best:
        raise SystemExit("没有可达的 ComfyUI 端口")
    return best[0]


def upload_ref(base, path):
    with open(path, "rb") as f:
        data = f.read()
    b = "----qwensubmit"
    ctype = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    fn = os.path.basename(path).encode("ascii", "ignore").decode() or "ref.png"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; "
            f"filename=\"{fn}\"\r\nContent-Type: {ctype}\r\n\r\n").encode() + \
           data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(base + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return json.loads(opener.open(req, timeout=120).read().decode())["name"]


def submit_and_wait(base, wf, poll=5, max_wait=900):
    pid = json.loads(opener.open(urllib.request.Request(base + "/prompt",
        data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"}), timeout=60).read())["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(poll)
        try:
            h = json.loads(get(f"{base}/history/{pid}"))
        except Exception:
            continue
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed") or st.get("status_str") == "error":
                return pid, h[pid]
    raise TimeoutError(f"timeout waiting {pid}")


def fetch_images(base, hist, out_dir, stem):
    saved = []
    for node_out in hist.get("outputs", {}).values():
        for im in node_out.get("images", []):
            if im.get("type") != "output":
                continue
            q = f"/view?filename={im['filename']}&subfolder={im.get('subfolder','')}&type={im['type']}"
            ext = os.path.splitext(im["filename"])[1] or ".png"
            dst = os.path.join(out_dir, stem + ext)
            with opener.open(base + q, timeout=120) as r, open(dst, "wb") as f:
                f.write(r.read())
            saved.append(dst)
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", choices=sorted(PRESETS), help="分辨率预设")
    ap.add_argument("--res", help="自定义分辨率, 如 832x1216")
    ap.add_argument("--width", type=int, help="自定义宽（与 --height 成对）")
    ap.add_argument("--height", type=int)
    ap.add_argument("--ref", help="参考图本地路径")
    ap.add_argument("--prompt", help="编辑指令（正向）")
    ap.add_argument("--prompt-file", help="从文件读编辑指令")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--prefix", default=None, help="SaveImage filename_prefix")
    ap.add_argument("--out", default="output", help="下载目录")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, help="8188 或 8189；不给自动挑显存空闲的")
    args = ap.parse_args()

    # ---- 分辨率解析与对齐 ----
    w = h = None
    if args.res:
        m = args.res.lower().replace("×", "x").split("x")
        if len(m) != 2 or not all(s.strip().isdigit() for s in m):
            raise SystemExit(f"--res 格式应为 WxH，收到: {args.res}")
        w, h = int(m[0]), int(m[1])
    elif args.width or args.height:
        if not (args.width and args.height):
            raise SystemExit("--width 和 --height 要成对给出")
        w, h = args.width, args.height
    elif args.preset:
        w, h = PRESETS[args.preset]
    if w:
        w = max(256, round(w / 16) * 16)
        h = max(256, round(h / 16) * 16)
        if w * h > 2_400_000:
            print(f"⚠ {w}x{h} 超过 Qwen-Image 2.1 常用像素范围(~2.2MP)，出图可能变慢或构图异常")

    prompt = args.prompt or (open(args.prompt_file, encoding="utf-8").read() if args.prompt_file else None)

    # ---- 组装工作流 ----
    wf = json.load(open(WF_PATH, encoding="utf-8"))
    base = pick_host(args.host, args.port)
    print("使用", base)
    if args.ref:
        ref = upload_ref(base, args.ref)
        print("上传参考图:", ref)
        wf["4"]["inputs"]["image"] = ref
    if prompt is not None:
        wf["5"]["inputs"]["prompt"] = prompt
    if w:
        wf["7"]["inputs"]["width"], wf["7"]["inputs"]["height"] = w, h
    wf["8"]["inputs"]["seed"] = args.seed if args.seed is not None else random.randint(1, 2**31 - 1)
    if args.prefix:
        wf["10"]["inputs"]["filename_prefix"] = args.prefix

    print(f"分辨率: {wf['7']['inputs']['width']}x{wf['7']['inputs']['height']}  "
          f"seed: {wf['8']['inputs']['seed']}")
    t0 = time.time()
    pid, hist = submit_and_wait(base, wf)
    st = hist.get("status", {})
    if st.get("status_str") == "error":
        for m in st.get("messages", []):
            if m[0] == "execution_error":
                raise SystemExit(f"执行失败: {m[1].get('node_type')} -> {m[1].get('exception_message')[:300]}")
        raise SystemExit("执行失败")

    os.makedirs(args.out, exist_ok=True)
    saved = fetch_images(base, hist, args.out, args.prefix or wf["10"]["inputs"]["filename_prefix"])
    print(f"完成 {time.time()-t0:.0f}s，出图 {len(saved)} 张:")
    for s in saved:
        print(" ", os.path.abspath(s))


if __name__ == "__main__":
    main()

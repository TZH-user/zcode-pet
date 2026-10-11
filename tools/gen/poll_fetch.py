# -*- coding: utf-8 -*-
"""轮询 ComfyUI 历史任务并取图（不重提交）"""
import json, sys, time, urllib.request

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
port, pid, out = sys.argv[1], sys.argv[2], sys.argv[3]
base = f"http://192.168.20.20:{port}"
t0 = time.time()
while time.time() - t0 < 1500:
    try:
        h = json.loads(op.open(f"{base}/history/{pid}", timeout=15).read().decode())
    except Exception as e:
        print("poll err", e, flush=True); time.sleep(15); continue
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            print("FAILED"); sys.exit(1)
        if st.get("completed"):
            for node in h[pid].get("outputs", {}).values():
                for im in node.get("images", []):
                    q = f"/view?filename={im['filename']}&subfolder={im.get('subfolder','')}&type={im['type']}"
                    data = op.open(base + q, timeout=120).read()
                    open(out, "wb").write(data)
                    print("saved", out, len(data)//1024, "KB")
                    sys.exit(0)
            print("completed but no images"); sys.exit(1)
    print(f"[{time.time()-t0:.0f}s] pending", flush=True)
    time.sleep(20)
print("TIMEOUT"); sys.exit(1)

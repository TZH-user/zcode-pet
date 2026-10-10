# -*- coding: utf-8 -*-
"""注册 ZCode hooks（幂等）：SessionStart/UserPromptSubmit 兜底拉起桌宠。

schema 依据 reference/zcode-src apps/zcode-cli/packages/adapters/src/config/schema.ts:
  hooks.events.<Event> = [ { matcher?, hooks: [ {type:"command", command, async, timeoutMs} ] } ]
注册后需重启 ZCode 客户端生效。
"""
import json
import os
import shutil
import time

P = os.path.expanduser("~/.zcode/cli/config.json")
CMD = 'powershell -NoProfile -ExecutionPolicy Bypass -File "F:\\Zcode\\桌宠\\tools\\hook\\pet-hook.ps1"'

backup = P + ".bak-pet2-" + time.strftime("%Y%m%d-%H%M%S")
shutil.copy(P, backup)
cfg = json.load(open(P, encoding="utf-8"))

h = cfg.setdefault("hooks", {})
h.pop("enabled", None)
ev = h.setdefault("events", {})
entry = {"hooks": [{"type": "command", "command": CMD, "async": True, "timeoutMs": 5000}]}
for e in ("SessionStart", "UserPromptSubmit"):
    ev[e] = [entry]

with open(P, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
json.load(open(P, encoding="utf-8"))  # 回读校验
print(f"hooks 已注册（备份 {os.path.basename(backup)}）——需重启 ZCode 客户端生效")

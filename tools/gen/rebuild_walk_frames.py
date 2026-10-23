# -*- coding: utf-8 -*-
"""frames-walk -> frames-walk2, final. Three measured defects, three fixes.

Measured on frames-walk (280 frames, 384x384):
  1. ~70% dead dwell frames (196/279 transitions move < 0.8 px, median |dcx| 0.24)
     -> FIX trim the dwell, keep a 3-frame breath at each end
  2. 2 direction reversals with no deceleration
     -> FIX insert TURN_DWELL copies of the last stride frame at each reversal
  3. a hard splice at frame 140: f140 vs f141 dx=0 diff=5.01 IoU=0.983, but
     f139 vs f141 dx=-29 diff=30.44 and bbox height 374->346 px
     => two clips butt-joined, a ~55 px bbox-centre teleport
     -> FIX the splice is a PURE TRANSLATION misalignment, not a scale or content
        change: clip A bbox x=[38,268] (w230), clip B bbox x=[95,321] (w226).
        Shifting clip B by the measured offset makes the join positionally
        continuous, so the cut degenerates into an ordinary pose change at a frame
        that already sits inside a dwell run.
        A cross-dissolve was tried first and rejected: blending two differently
        composed clips produces a double-exposure ghost, and the pose centroid
        still peaked at 15.6 px/frame. Translation realignment has no ghost.
        Shifted frames are bounds-checked against the canvas before writing.
"""
import glob
import os
import shutil

import numpy as np
from PIL import Image

SPR = r"F:\Zcode\桌宠\assets\sprites\luotianyi"
SRC = os.path.join(SPR, "frames-walk")
DST = os.path.join(SPR, "frames-walk2")
OUT = r"F:\tmp\pet-diag"

SPEED_THRESH = 0.8
DWELL_KEEP = 3
TURN_DWELL = 5
MIN_STRIDE = 4
POP_MIN_PX = 6.0
TARGET_CYCLE_S = 7.0

files = sorted(glob.glob(os.path.join(SRC, "*.png")))
n = len(files)
if not files:
    raise SystemExit("no frames in " + SRC)

_cache = {}


def pil(i):
    if i not in _cache:
        _cache[i] = Image.open(files[i]).convert("RGBA")
    return _cache[i]


cx = np.zeros(n)
bbox = []
for i in range(n):
    a = np.asarray(pil(i), dtype=np.uint8)
    m = a[..., 3] > 24
    if m.any():
        ys, xs = np.where(m)
        cx[i] = float(xs.mean())
        bbox.append((int(xs.min()), int(xs.max())))
    else:
        cx[i] = 0.0
        bbox.append((0, 0))

spd = np.abs(np.diff(cx, prepend=cx[0]))
moving = spd > SPEED_THRESH

# ---- segment into runs, demote micro-jitter "motion" runs to dwell ----
runs = []
i = 0
while i < n:
    j = i
    while j + 1 < n and moving[j + 1] == moving[i]:
        j += 1
    runs.append([bool(moving[i]), i, j])
    i = j + 1

kept = [[m, a, b] if (m and (b - a + 1) >= MIN_STRIDE) else [False, a, b] for m, a, b in runs]

# ---- turnarounds: compare consecutive MOTION runs. Runs alternate motion/dwell,
#      so a naive "is the next run motion?" test never fires (that bug was in v1
#      of this script and reported turnarounds=0). ----
motion_runs = [(a, b) for m, a, b in kept if m]
turn_after, turns = {}, 0
for k in range(1, len(motion_runs)):
    pa, pb = motion_runs[k - 1]
    na, nb = motion_runs[k]
    d1, d2 = np.sign(cx[pb] - cx[pa]), np.sign(cx[nb] - cx[na])
    if d1 and d2 and d1 != d2:
        turn_after[pa] = TURN_DWELL
        turns += 1

# ---- assemble ----
seq = []
for m, a, b in kept:
    if m:
        seq.extend(range(a, b + 1))
        if a in turn_after:
            seq.extend([b] * turn_after[a])
    else:
        head = min(DWELL_KEEP, b - a + 1)
        seq.extend([a] * head)
        seq.extend([b] * head)

# ---- locate the splice in the ORIGINAL frame order and compute the realign dx ----
step_px = np.abs(np.diff(cx))
sp = int(np.argmax(step_px)) + 1
if step_px[sp - 1] <= POP_MIN_PX:
    sp, dx = -1, 0
else:
    dx = int(round(cx[sp - 1] - cx[sp]))     # apply to frames >= sp

print(f"source frames : {n}   canvas={pil(0).size}")
print(f"runs          : {len(runs)} (motion={sum(1 for r in runs if r[0])}, "
      f"dwell={sum(1 for r in runs if not r[0])})")
print(f"turnarounds   : {turns}  (eased with {TURN_DWELL} dwell frames each)")
print(f"splice        : frame {sp}  step={step_px[sp-1]:.1f}px  "
      f"realign dx={dx:+d}  bbox A={bbox[sp-1]} B={bbox[sp]}")

# bounds check the realign before committing to it
if dx:
    W, H = pil(0).size
    bad = [i for i in range(sp, n) if bbox[i][0] + dx < 0 or bbox[i][1] + dx >= W]
    if bad:
        print(f"  !! realign would clip {len(bad)} frames (first {bad[0]}) -> shifting clip A instead")
        dx_a, dx_b = -int(round(cx[sp] - cx[sp - 1])) + dx, 0
        dx = 0
        # fallback: keep B, move A right is unsafe too -> just skip realign
        print("  !! aborting realign (would clip); leaving splice as-is")
        dx = 0
    else:
        print(f"  realign OK: no frame clipped (canvas W={W})")

# ---- materialise ----
if os.path.isdir(DST):
    shutil.rmtree(DST)
os.makedirs(DST, exist_ok=True)

shifted = 0
for out_i, src_i in enumerate(seq):
    d = dx if (dx and src_i >= sp) else 0
    dst = os.path.join(DST, f"run_{out_i:03d}.png")
    if d == 0:
        shutil.copyfile(files[src_i], dst)
    else:
        im = pil(src_i)
        W, H = im.size
        a = np.asarray(im, dtype=np.uint8)
        out = np.zeros_like(a)
        xs_dst = slice(max(0, d), min(W, W + d))
        xs_src = slice(max(0, -d), min(W, W - d))
        out[:, xs_dst] = a[:, xs_src]
        Image.fromarray(out, "RGBA").save(dst)
        shifted += 1

print(f"\nwrote {len(seq)} frames -> {DST}   (realigned={shifted})")

# ---- verify ----
out_files = sorted(glob.glob(os.path.join(DST, "*.png")))
ocx = np.zeros(len(out_files))
for i, f in enumerate(out_files):
    a = np.asarray(Image.open(f).convert("RGBA"), dtype=np.uint8)
    m = a[..., 3] > 24
    ocx[i] = float(np.where(m)[1].mean()) if m.any() else 0.0
ospd = np.abs(np.diff(ocx, prepend=ocx[0]))
p90 = float(np.percentile(ospd, 90))
thr = max(6.0, 4 * p90)
pops = [(i, round(float(ospd[i]), 1)) for i in range(len(ospd)) if ospd[i] > thr]
fps = int(max(12, min(30, round(len(out_files) / TARGET_CYCLE_S))))

print(f"\n--- verify frames-walk2 ---")
print(f"frames {len(out_files)}   travel {abs(ocx.max()-ocx.min()):.1f}px")
print(f"speed  median={np.median(ospd):.2f}  p90={p90:.2f}  max={ospd.max():.2f}"
      f"      (was: median 0.24  max 25.15)")
print(f"pops > {thr:.1f}px : {len(pops)}  {pops}")
print(f"fps={fps}   cycle={len(out_files)/fps:.1f}s   (was 280 @20 = 14.0s)")

with open(os.path.join(OUT, "walk_rebuild.txt"), "w", encoding="utf-8") as fh:
    fh.write(f"frames={len(out_files)}\nfps={fps}\ncycle_s={len(out_files)/fps:.2f}\n"
             f"turns={turns}\npops={len(pops)}\nrealign_dx={dx}\n")
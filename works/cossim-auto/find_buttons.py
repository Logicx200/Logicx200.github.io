# -*- coding: utf-8 -*-
"""定位仿真工具栏按钮（y≈125..175 的文字段）。"""
import os
import sys
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto"
name = sys.argv[1] if len(sys.argv) > 1 else "03_sim_tab2.png"
im = np.asarray(Image.open(os.path.join(OUT, name)).convert("RGB")).astype(int)

y0, y1 = 125, 178
band = im[y0:y1]
bright = (band[:, :, 0] > 120) & (band[:, :, 1] > 120) & (band[:, :, 2] > 120)
col = bright.sum(axis=0)
segs, in_seg = [], False
for x, v in enumerate(col):
    if v >= 2 and not in_seg:
        s, in_seg = x, True
    elif v < 2 and in_seg:
        segs.append((s, x - 1)); in_seg = False
if in_seg:
    segs.append((s, len(col) - 1))
merged = []
for s in segs:
    if merged and s[0] - merged[-1][1] <= 22:
        merged[-1] = (merged[-1][0], s[1])
    else:
        merged.append(list(s))
print(f"y={y0}..{y1} 共 {len(merged)} 段：")
for i, (a, b) in enumerate(merged):
    print(f"  {i}: x={a}-{b} center={int((a+b)/2)}")

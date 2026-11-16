# -*- coding: utf-8 -*-
"""自动定位顶部导航 tab 的文字框（亮度阈值 + 列投影分段）。"""
import os
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto"
im = np.asarray(Image.open(os.path.join(OUT, "02_sim_tab.png")).convert("RGB")).astype(int)

# 导航栏大致在 y=85..115
band = im[85:118]
bright = (band[:, :, 0] > 110) & (band[:, :, 1] > 110) & (band[:, :, 2] > 110)
col = bright.sum(axis=0)
# 只保留文字密度足够且位于左半区
segs = []
in_seg = False
for x, v in enumerate(col):
    if v >= 2 and not in_seg:
        start, in_seg = x, True
    elif v < 2 and in_seg:
        segs.append((start, x - 1)); in_seg = False
if in_seg:
    segs.append((start, len(col) - 1))

# 合并间距 < 12px 的相邻段（同一汉字/词内）
merged = []
for s in segs:
    if merged and s[0] - merged[-1][1] <= 12:
        merged[-1] = (merged[-1][0], s[1])
    else:
        merged.append(list(s))
print("检测到文字段:", len(merged))
labels = ["方案", "时空", "环境", "传感器", "目标", "场景", "干扰", "仿真", "制备"]
for i, (a, b) in enumerate(merged):
    lab = labels[i] if i < len(labels) else "?"
    print(f"  {i}: x={a}-{b} center={int((a+b)/2)} y={101} 猜测={lab}")

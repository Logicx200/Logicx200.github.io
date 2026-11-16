# -*- coding: utf-8 -*-
"""精确定位渲染区左右边界（用行段内的亮度/方差特征）。"""
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
im = Image.open(OUT + r"\01_preview_window.png").convert("RGB")
a = np.asarray(im).astype(float)
lum = a.mean(axis=2)
y0, y1 = 66, 721
sub = lum[y0:y1 + 1]

col_std = sub.std(axis=0)
col_mean = sub.mean(axis=0)
# 打印关键区间的统计
for x in list(range(80, 105)) + list(range(1105, 1125)):
    print(f"x={x:4d} mean={col_mean[x]:6.1f} std={col_std[x]:6.1f}")

# 图像区：列均值 > 25 且列方差 > 12 的最长连续段
mask = (col_std > 12) & (col_mean > 20)
segs, s = [], None
for i, v in enumerate(mask):
    if v and s is None:
        s = i
    elif not v and s is not None:
        segs.append((s, i - 1)); s = None
if s is not None:
    segs.append((s, len(mask) - 1))
big = [t for t in segs if t[1] - t[0] > 100]
print("列段:", big)
x0, x1 = max(big, key=lambda t: t[1] - t[0])
print(f"图像区: x {x0}..{x1} w={x1-x0+1}, y {y0}..{y1} h={y1-y0+1}, 宽高比={(x1-x0+1)/(y1-y0+1):.4f}")
crop = im.crop((x0, y0, x1 + 1, y1 + 1))
crop.save(OUT + r"\02_render.png")
print("saved 02_render.png", crop.size)

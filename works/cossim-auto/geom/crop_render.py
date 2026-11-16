# -*- coding: utf-8 -*-
"""精确裁出预览窗渲染区（1024x768），并输出跑道 ROI 放大图。"""
import os
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
im = Image.open(os.path.join(OUT, "01_preview_window.png")).convert("RGB")
a = np.asarray(im).astype(int)
H, W, _ = a.shape
print("window:", im.size)

# 渲染区判定：灰度内容（通道差很小）且亮度有起伏
grayish = (np.abs(a[..., 0] - a[..., 1]) < 8) & (np.abs(a[..., 1] - a[..., 2]) < 8)
sat = a.max(axis=2) - a.min(axis=2)
content = grayish & (sat < 20)
row_frac = content.mean(axis=1)
col_frac = content.mean(axis=0)

rows = np.where(row_frac > 0.5)[0]
cols = np.where(col_frac > 0.5)[0]
print("灰度行范围:", rows.min(), rows.max(), " 灰度列范围:", cols.min(), cols.max())
print("行占比前 5 行:", rows[:5], " 后 5 行:", rows[-5:])

# 用亮度方差进一步锁定真正的图像区
lum = a.mean(axis=2)
row_std = lum.std(axis=1)
# 找到连续的、std>10 的行段
mask = row_std > 10
segs, s = [], None
for i, v in enumerate(mask):
    if v and s is None:
        s = i
    elif not v and s is not None:
        segs.append((s, i - 1)); s = None
if s is not None:
    segs.append((s, len(mask) - 1))
print("行段(std>10):", [(a_, b_, b_ - a_ + 1) for a_, b_ in segs if b_ - a_ > 50])

y0, y1 = max(segs, key=lambda t: t[1] - t[0])
xs = np.where(lum[y0:y1].std(axis=0) > 10)[0]
x0, x1 = int(xs.min()), int(xs.max())
print(f"渲染区: x {x0}..{x1} (w={x1-x0+1}), y {y0}..{y1} (h={y1-y0+1})")

crop = im.crop((x0, y0, x1 + 1, y1 + 1))
crop.save(os.path.join(OUT, "02_render.png"))
print("裁剪:", crop.size, "宽高比:", round(crop.size[0] / crop.size[1], 4), "(1024/768=1.3333)")

# 跑道 ROI：图像上部
roi = crop.crop((80, 0, 700, 160))
roi = roi.resize((roi.size[0] * 2, roi.size[1] * 2), Image.LANCZOS)
roi.save(os.path.join(OUT, "03_runway_roi.png"))
print("跑道 ROI:", roi.size, "-> 03_runway_roi.png")

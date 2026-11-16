# -*- coding: utf-8 -*-
"""沿跑道轴向统计白色标志密度，定位两端入口标志（piano keys）。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(p, flags=cv2.IMREAD_GRAYSCALE):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), flags)


img = imread_u(os.path.join(OUT, "02_render_1024.png")).astype(float)
H, W = img.shape
p1 = np.array([147.0, 116.0]); p2 = np.array([572.0, 4.0])
d = p2 - p1; L = np.linalg.norm(d); u = d / L
n = np.array([-u[1], u[0]])

ys, xs = np.mgrid[0:H, 0:W]
rel = np.stack([xs - p1[0], ys - p1[1]], axis=-1)
t = rel @ u
s = rel @ n

# 跑道内部（两条边线之间）：s ∈ [-19, -10]
inside = (s > -19.5) & (s < -9.5) & (t > -15) & (t < L + 15)
for thr in (110, 120, 130):
    bright = (img > thr) & inside
    tt = t[bright]
    if len(tt) < 20:
        print(f"thr={thr}: 亮像素太少 {len(tt)}")
        continue
    bins = np.arange(-15, L + 16, 2.0)
    hist, edges = np.histogram(tt, bins=bins)
    hs = np.convolve(hist, np.ones(3) / 3, mode="same")
    # 找两端第一个/最后一个显著峰
    th = max(1.5, hs.max() * 0.15)
    idx = np.where(hs >= th)[0]
    if len(idx) == 0:
        print(f"thr={thr}: 无显著峰 (max hist={hist.max()})")
        continue
    i_first, i_last = idx[0], idx[-1]
    c_first = 0.5 * (edges[i_first] + edges[i_first + 1])
    c_last = 0.5 * (edges[i_last] + edges[i_last + 1])
    print(f"thr={thr}: 亮像素={len(tt)}, 峰数={len(idx)}, "
          f"首峰 t={c_first:.1f}, 末峰 t={c_last:.1f}, 跨度={c_last-c_first:.1f} px, "
          f"→ GSD(2000m)={2000.0/(c_last-c_first):.3f} m/px")
    # 打印直方图包络摘要
    prof = [(round(0.5 * (edges[i] + edges[i + 1]), 1), int(hs[i])) for i in range(len(hs)) if hs[i] >= th]
    print("   显著区段:", prof[:20], "..." if len(prof) > 20 else "")

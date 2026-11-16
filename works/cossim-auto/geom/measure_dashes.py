# -*- coding: utf-8 -*-
"""沿跑道轴向检测中心线虚线，统计虚线周期 → 反算 GSD。"""
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

# 跑道内部带（两条边线之间，去掉边线本身）
inside = (s < -11.5) & (s > -17.5) & (t > 0) & (t < L)
bright = (img > 115) & inside
tt = t[bright]
print("跑道内亮像素:", len(tt))

# 沿 t 的直方图（0.5 px 分箱）→ 找虚线簇
bins = np.arange(0, L + 0.5, 0.5)
hist, edges = np.histogram(tt, bins=bins)
# 平滑后找峰
k = np.ones(3) / 3
hs = np.convolve(hist, k, mode="same")
thr = max(2.0, hs.max() * 0.25)
peaks = [i for i in range(1, len(hs) - 1) if hs[i] >= thr and hs[i] >= hs[i - 1] and hs[i] >= hs[i + 1]]
# 合并邻近峰
merged = []
for i in peaks:
    c = 0.5 * (edges[i] + edges[i + 1])
    if merged and c - merged[-1] < 4:
        merged[-1] = 0.5 * (merged[-1] + c)
    else:
        merged.append(c)
print(f"检测到虚线簇 {len(merged)} 个")
if len(merged) >= 3:
    diffs = np.diff(merged)
    print("相邻簇间距(px):", np.round(diffs, 2).tolist())
    med = float(np.median(diffs))
    print(f"中位间距 = {med:.2f} px")
    print(f"若 ICAO 周期 50 m → GSD = {50/med:.3f} m/px")
    print(f"若周期 60 m → GSD = {60/med:.3f} m/px")
    print(f"若周期 75 m → GSD = {75/med:.3f} m/px")
    print(f"整段 {L:.1f} px 对应距离 = {L*50/med:.0f} m (按 50 m 周期)")

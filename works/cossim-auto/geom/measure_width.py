# -*- coding: utf-8 -*-
"""沿跑道法向做亮线投影，客观测跑道宽度；并用两条边缘线求长度。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(p, flags=cv2.IMREAD_GRAYSCALE):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), flags)


img = imread_u(os.path.join(OUT, "02_render_1024.png")).astype(float)
H, W = img.shape

# 跑道方向（从最长边线拟合）
p1 = np.array([147.0, 116.0]); p2 = np.array([572.0, 4.0])
d = (p2 - p1); L = np.linalg.norm(d); u = d / L
n = np.array([-u[1], u[0]])
print(f"跑道方向角: {np.degrees(np.arctan2(u[1], u[0])):.2f}°, 参考长度 {L:.1f} px")

# 在跑道中段取一个窗口，沿法向投影亮像素
ys, xs = np.mgrid[0:H, 0:W]
rel = np.stack([xs - p1[0], ys - p1[1]], axis=-1)
t = rel @ u          # 沿跑道坐标
s = rel @ n          # 法向坐标
window = (t > 100) & (t < 340)      # 跑道中段
bright = (img > 120) & window
svals = s[bright]
print("窗口内亮像素:", len(svals))
hist, edges = np.histogram(svals, bins=np.arange(-40, 40, 0.5))
top = np.argsort(hist)[::-1][:12]
print("法向亮像素峰值（s, count）:")
for i in sorted(top):
    print(f"  s={0.5*(edges[i]+edges[i+1]):7.2f}  n={hist[i]:5d}")

# 也给出中心线（长虚线）位置：可能在两条边线之间
center = 0.5 * (edges[top[0]] + edges[top[0] + 1])
print("最亮位置 s=", round(center, 2))

# -*- coding: utf-8 -*-
"""用入口标志（piano keys）白点密度定位跑道两端，并做几何换算。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(p, flags=cv2.IMREAD_GRAYSCALE):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), flags)


img = imread_u(os.path.join(OUT, "02_render_1024.png"))
print("image", img.shape)

# 取跑道带：沿跑道方向做旋转对齐（角度约 -14.5°）
H, W = img.shape
ang = -14.5
M = cv2.getRotationMatrix2D((W / 2, 60), ang, 1.0)
rot = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
cv2.imwrite = None  # noqa
ok, buf = cv2.imencode(".png", rot)
buf.tofile(os.path.join(OUT, "09_rot.png"))
print("rotated saved")

# 旋转后跑道应水平；在其所在行带里找亮标线密度
band = rot[20:90]
_, bw = cv2.threshold(band, 125, 255, cv2.THRESH_BINARY)
bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
col = (bw > 0).sum(axis=0).astype(float)
# 平滑
k = np.ones(9) / 9
cs = np.convolve(col, k, mode="same")
print("列密度（每 20 px 采样）:")
for x in range(0, W, 20):
    print(f"  x={x:4d} density={cs[x]:6.1f}")
np.save(os.path.join(OUT, "coldensity.npy"), cs)

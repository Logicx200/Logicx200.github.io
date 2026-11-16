# -*- coding: utf-8 -*-
"""跑道边缘直线检测（兼容中文路径）。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(path, flags=cv2.IMREAD_GRAYSCALE):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)


def imwrite_u(path, img):
    ok, buf = cv2.imencode(os.path.splitext(path)[1], img)
    if ok:
        buf.tofile(path)


img = imread_u(os.path.join(OUT, "02_render_1024.png"))
print("图像:", img.shape)

roi_y0, roi_y1 = 0, 170
roi = img[roi_y0:roi_y1]
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
eq = clahe.apply(roi)
_, bw = cv2.threshold(eq, 140, 255, cv2.THRESH_BINARY)
bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
imwrite_u(os.path.join(OUT, "04_mask.png"), bw)

lines = cv2.HoughLinesP(bw, 1, np.pi / 720, threshold=60, minLineLength=120, maxLineGap=25)
print("候选线段:", 0 if lines is None else len(lines))
cands = []
if lines is not None:
    for l in lines[:, 0, :]:
        x1, y1, x2, y2 = map(float, l)
        L = float(np.hypot(x2 - x1, y2 - y1))
        ang = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        cands.append((L, ang, x1, y1 + roi_y0, x2, y2 + roi_y0))
cands.sort(reverse=True)
print(f"{'len':>7} {'angle':>7}   (x1,y1)-(x2,y2)")
for c in cands[:16]:
    L, ang, x1, y1, x2, y2 = c
    print(f"{L:7.1f} {ang:7.2f}   ({x1:6.1f},{y1:5.1f})-({x2:6.1f},{y2:5.1f})")

# 保存标注图
vis = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
for c in cands[:8]:
    _, _, x1, y1, x2, y2 = c
    cv2.line(vis, (int(x1), int(y1 - roi_y0)), (int(x2), int(y2 - roi_y0)), (0, 0, 255), 1)
imwrite_u(os.path.join(OUT, "05_lines_vis.png"), vis)
print("saved 04_mask.png / 05_lines_vis.png")

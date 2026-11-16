# -*- coding: utf-8 -*-
"""把候选跑道线画回图像，核对哪条才是主跑道。"""
import os
import numpy as np
import cv2

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"


def imread_u(p, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), flags)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(os.path.splitext(p)[1], img)
    if ok:
        buf.tofile(p)


img = imread_u(os.path.join(OUT, "02_render_1024.png"))
cands = {
    "A_hough_longest": ((147, 116), (572, 4), (0, 0, 255)),
    "B_my_read": ((168, 82), (556, 7), (0, 255, 0)),
    "C_taxiway_guess": ((150, 118), (420, 55), (255, 0, 0)),
}
for name, ((x1, y1), (x2, y2), color) in cands.items():
    cv2.line(img, (x1, y1), (x2, y2), color, 1)
    cv2.circle(img, (x1, y1), 3, color, -1)
    cv2.circle(img, (x2, y2), 3, color, -1)
crop = img[0:140, 100:620]
crop = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3), interpolation=cv2.INTER_LANCZOS4)
imwrite_u(os.path.join(OUT, "11_candidates.png"), crop)
print("saved 11_candidates.png")

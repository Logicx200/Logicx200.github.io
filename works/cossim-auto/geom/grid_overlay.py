# -*- coding: utf-8 -*-
"""生成带坐标网格的跑道放大图，便于人工判读端点。"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
im = Image.open(os.path.join(OUT, "02_render_1024.png")).convert("RGB")

box = (95, 0, 625, 125)
x0, y0 = box[0], box[1]
crop = im.crop(box)
S = 4
crop = crop.resize((crop.size[0] * S, crop.size[1] * S), Image.LANCZOS)
d = ImageDraw.Draw(crop)
try:
    font = ImageFont.truetype("arial.ttf", 14)
except Exception:
    font = ImageFont.load_default()

# 网格：每 10 渲染像素
for gx in range(x0 - x0 % 10, box[2], 10):
    px = (gx - x0) * S
    col = (255, 80, 80) if gx % 50 == 0 else (90, 90, 90)
    d.line([(px, 0), (px, crop.size[1])], fill=col, width=1)
    if gx % 50 == 0:
        d.text((px + 2, 2), str(gx), fill=(255, 200, 0), font=font)
for gy in range(0, box[3] - y0, 10):
    py = gy * S
    col = (255, 80, 80) if gy % 50 == 0 else (90, 90, 90)
    d.line([(0, py), (crop.size[0], py)], fill=col, width=1)
    if gy % 50 == 0:
        d.text((2, py + 1), str(gy), fill=(255, 200, 0), font=font)

crop.save(os.path.join(OUT, "10_runway_grid.png"))
print("saved 10_runway_grid.png", crop.size, "box=", box, "scale=", S)

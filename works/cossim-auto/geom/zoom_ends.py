# -*- coding: utf-8 -*-
"""放大跑道左右两端，便于确定精确端点。"""
import os
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
im = Image.open(os.path.join(OUT, "02_render_1024.png")).convert("L")

regions = {
    "06_runway_left.png": (80, 55, 260, 130),    # 左端
    "07_runway_right.png": (480, 0, 640, 70),    # 右端
    "08_runway_mid.png": (250, 30, 450, 100),    # 中段（边线/宽度）
}
for name, box in regions.items():
    c = im.crop(box)
    c = c.resize((c.size[0] * 6, c.size[1] * 6), Image.LANCZOS)
    c.save(os.path.join(OUT, name))
    print(name, box, "->", c.size)

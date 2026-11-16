# -*- coding: utf-8 -*-
"""裁出屏幕 1:1 渲染区（1024x656 可见部分），输出跑道放大图。"""
import os
import numpy as np
from PIL import Image

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
im = Image.open(os.path.join(OUT, "01_preview_window.png")).convert("RGB")

X0, Y0 = 92, 66          # 图像左上角在窗口内的位置
W, H_VIS = 1024, 656     # 1:1 显示，底部被窗口裁掉
render = im.crop((X0, Y0, X0 + W, Y0 + H_VIS))
render.save(os.path.join(OUT, "02_render_1024.png"))
print("render:", render.size, "(应为 1024x656)")

# 跑道 ROI（图像上部）
roi = render.crop((60, 0, 640, 130)).resize((580 * 3, 130 * 3), Image.LANCZOS)
roi.save(os.path.join(OUT, "03_runway_roi.png"))
print("跑道 ROI:", roi.size)

arr = np.asarray(render.convert("L"))
print("渲染区亮度: min=%d max=%d mean=%.1f std=%.1f" % (arr.min(), arr.max(), arr.mean(), arr.std()))

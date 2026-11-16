# -*- coding: utf-8 -*-
"""裁剪界面关键区域，便于核对坐标。"""
from PIL import Image
import os

OUT = r"F:\DeepSeek工作区\_cossim_auto"
src = os.path.join(OUT, "01_launch.png")
im = Image.open(src)
print("size:", im.size)

crops = {
    "crop_topbar.png": (0, 60, 1200, 180),      # 导航 tab + 工具按钮
    "crop_topright.png": (1200, 0, 1920, 190),  # 右侧最小化/关闭
    "crop_bottom.png": (0, 880, 1920, 1032),    # 运行日志/状态
}
for name, box in crops.items():
    im.crop(box).save(os.path.join(OUT, name))
    print(name, box)

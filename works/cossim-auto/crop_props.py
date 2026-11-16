# -*- coding: utf-8 -*-
"""裁剪右侧属性面板，便于精确定位单元格。"""
from PIL import Image
import os
OUT = r"F:\DeepSeek工作区\_cossim_auto"
im = Image.open(os.path.join(OUT, "08_click_scene.png"))
box = (1477, 190, 1920, 440)
im.crop(box).resize(((box[2]-box[0])*2, (box[3]-box[1])*2)).save(os.path.join(OUT, "crop_props.png"))
print("saved crop_props.png", box)

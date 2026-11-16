# -*- coding: utf-8 -*-
"""测试顶部导航“方案”是否切换页面。"""
import ctypes, os, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=2.0):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(n):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, n))


def probe():
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)
    # 方案页工具栏：x 30-560, y 145-180 区域内亮像素分布
    band = a[145:180, 20:620]
    col = (band > 110).sum(axis=0)
    segs, s = [], None
    for i, v in enumerate(col):
        if v >= 2 and s is None:
            s = i
        elif v < 2 and s is not None:
            segs.append((s + 20, i - 1 + 20)); s = None
    if s is not None:
        segs.append((s + 20, 619))
    merged = []
    for a_, b_ in segs:
        if merged and a_ - merged[-1][1] <= 18:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [(int((x + y) / 2)) for x, y in merged if y - x >= 18]


print("点击前:", probe())
click(64, 101)
shot("83_nav_plan.png")
print("点击方案导航后:", probe())

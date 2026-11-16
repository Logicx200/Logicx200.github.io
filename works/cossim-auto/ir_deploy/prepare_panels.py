# -*- coding: utf-8 -*-
"""进入制备页 -> 像素定位工具栏 -> 依次打开 材质/热特性/大气 面板。"""
import ctypes, os, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)


def segments(y0, y1, x0=0, x1=900):
    a = np.asarray(Image.open(os.path.join(OUT, "_tmp.png")).convert("L")).astype(int)
    band = a[y0:y1, x0:x1]
    col = (band > 115).sum(axis=0)
    segs, s = [], None
    for i, v in enumerate(col):
        if v >= 2 and s is None:
            s = i
        elif v < 2 and s is not None:
            segs.append((s + x0, i - 1 + x0)); s = None
    if s is not None:
        segs.append((s + x0, len(col) - 1 + x0))
    merged = []
    for a_, b_ in segs:
        if merged and a_ - merged[-1][1] <= 20:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [(int((a_ + b_) / 2), int((y0 + y1) / 2)) for a_, b_ in merged if b_ - a_ >= 20]


click(900, 101, 2.0)          # 制备
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "_tmp.png"))
btns = segments(130, 180, 0, 900)
print("制备页工具栏按钮:", btns)
shot("44_prepare_page.png")
if len(btns) >= 4:
    click(btns[2][0], btns[2][1], 2.5)     # 热特性模型
    shot("45_thermal.png")
    click(btns[3][0], btns[3][1], 2.5)     # 大气模型
    shot("46_atmo.png")
    click(btns[1][0], btns[1][1], 2.5)     # 材质模型
    shot("47_material.png")

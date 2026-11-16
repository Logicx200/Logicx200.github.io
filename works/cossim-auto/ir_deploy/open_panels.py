# -*- coding: utf-8 -*-
"""打开“热特性模型”和“大气模型”面板截图。"""
import ctypes, os, time
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=2.0):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)


# 制备页工具栏（从 40_prepare_tab.png 读）：模型管理~86 材质模型~215 热特性模型~330 大气模型~455（abs 坐标）
click(330, 157)
shot("42_thermal_panel.png")
click(455, 157)
shot("43_atmo_panel.png")

# -*- coding: utf-8 -*-
"""点击顶部导航各页，寻找传感器预览入口。"""
import ctypes, os, time
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=1.8):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)


# 顶部导航坐标（来自前面的像素定位）：方案64 时空170 环境278 传感器386 目标492 场景598 干扰706 仿真812 制备~900
click(386, 101)
shot("34_sensor_tab.png")
click(492, 101)
shot("35_target_tab.png")

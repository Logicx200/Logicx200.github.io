# -*- coding: utf-8 -*-
"""查看“制备”页，确认热特性/大气/材质插件是否已启用。"""
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


click(182, 1013, 1.2)     # 先回方案页（避免停在配置模式）
click(900, 101)
shot("40_prepare_tab.png")
click(278, 101)           # 环境页
shot("41_env_tab.png")

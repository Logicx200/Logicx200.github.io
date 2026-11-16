# -*- coding: utf-8 -*-
"""精确选中 中波红外_0，裁剪右侧属性面板。"""
import ctypes, os, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


for y in (474, 481, 470):
    click(86, y)
    ImageGrab.grab(all_screens=False).crop((1480, 185, 1920, 420)).resize((880, 470)).save(
        os.path.join(OUT, f"54_props_y{y}.png"))
    print("saved", f"54_props_y{y}.png")

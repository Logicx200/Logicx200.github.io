# -*- coding: utf-8 -*-
"""切到“配置”页，查看模型库树中的传感器条目。"""
import ctypes, os, time
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


click(27, 1013)     # 配置
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "31_config_tab.png"))
print("saved 31_config_tab.png")
# 放大左侧树，便于读条目
ImageGrab.grab(all_screens=False).crop((0, 180, 330, 1032)).resize((660, 1704)).save(
    os.path.join(OUT, "32_tree_zoom.png"))
print("saved 32_tree_zoom.png")

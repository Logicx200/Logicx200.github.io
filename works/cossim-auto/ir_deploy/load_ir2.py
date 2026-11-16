# -*- coding: utf-8 -*-
"""点击“打开”并载入 IR 想定（固定坐标 + 截图验证）。"""
import ctypes, os, time
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PLAN = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\Anchor_F16_yngd_IR.xml"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)


click(175, 161)
shot("27_after_open_click.png")
print("若截图里出现文件对话框，继续输入路径")
send_keys("%n"); time.sleep(0.6)
send_keys("^a"); time.sleep(0.1)
send_keys(PLAN, with_spaces=True); time.sleep(0.6)
send_keys("{ENTER}"); time.sleep(9.0)
shot("28_loaded_ir.png")

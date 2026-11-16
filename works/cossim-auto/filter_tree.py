# -*- coding: utf-8 -*-
"""在左侧搜索框输入关键词并截图，用于定位中波红外传感器。"""
import ctypes, os, time
import win32clipboard
from PIL import ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto"
_u = ctypes.windll.user32


def click(x, y, pause=1.0):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def set_clip(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


set_clip("中波")
click(175, 288)          # 左侧搜索框（配置树）
time.sleep(0.3)
send_keys("^a"); time.sleep(0.1)
send_keys("^v"); time.sleep(1.5)
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "51_filter.png"))
print("saved 51_filter.png")

# -*- coding: utf-8 -*-
"""稳妥载入探针想定：打开->Alt+N->粘贴路径->Enter，每步截图。"""
import ctypes, os, time
import win32clipboard
import numpy as np
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PLAN = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\_probe_atmo.xml"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name, flush=True)


def has_dialog():
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L"))
    # 文件对话框通常在中部有一块亮区（白/浅灰）
    c = a[250:800, 400:1500]
    return float((c > 180).mean()) > 0.08


def clip(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


clip(PLAN)
click(175, 161, 2.5)
shot("72_dialog.png")
print("检测到对话框:", has_dialog())
if has_dialog():
    send_keys("%n"); time.sleep(0.5)
    send_keys("^a"); time.sleep(0.15)
    send_keys("^v"); time.sleep(0.6)
    shot("73_path_typed.png")
    send_keys("{ENTER}"); time.sleep(9.0)
    shot("74_after_load.png")
    raw = open(LOG, "rb").read().decode("gb18030", errors="replace")
    lines = [l.strip() for l in raw.splitlines() if "setModelVisible" not in l][-12:]
    print("日志尾部:")
    for l in lines:
        print("  ", l[:150])

# -*- coding: utf-8 -*-
"""切方案页 -> 找工具栏打开按钮 -> 载入探针想定。"""
import ctypes, os, time
import numpy as np
import win32clipboard
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


def toolbar(x0=0, x1=700, y0=140, y1=190):
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)
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
        if merged and a_ - merged[-1][1] <= 25:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [(int((a_ + b_) / 2), int((y0 + y1) / 2)) for a_, b_ in merged if b_ - a_ >= 25]


def has_dialog():
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L"))
    c = a[250:800, 400:1500]
    return float((c > 170).mean()) > 0.06


def clip(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


click(182, 1013, 2.0)          # 方案页
btns = toolbar()
print("工具栏按钮:", btns[:6])
if len(btns) >= 2:
    clip(PLAN)
    click(btns[1][0], btns[1][1], 2.5)
    shot("75_dialog.png")
    ok = has_dialog()
    print("对话框:", ok)
    if ok:
        send_keys("%n"); time.sleep(0.5)
        send_keys("^a"); time.sleep(0.15)
        send_keys("^v"); time.sleep(0.6)
        shot("76_typed.png")
        send_keys("{ENTER}"); time.sleep(9.0)
        shot("77_loaded.png")
        raw = open(LOG, "rb").read().decode("gb18030", errors="replace")
        lines = [l.strip() for l in raw.splitlines()
                 if "setModelVisible" not in l][-10:]
        print("日志尾部:")
        for l in lines:
            print("  ", l[:150])

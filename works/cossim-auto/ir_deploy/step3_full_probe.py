# -*- coding: utf-8 -*-
"""S0 探针完整流程：载入探针想定 -> 仿真准备 -> 抓取格式报错。"""
import ctypes, os, time
import numpy as np
import win32clipboard
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PLAN = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\_probe_atmo.xml"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.8):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(n):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, n))


def segs(x0, x1, y0=145, y1=180, thr=110, minw=18):
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)
    band = a[y0:y1, x0:x1]
    col = (band > thr).sum(axis=0)
    out, s = [], None
    for i, v in enumerate(col):
        if v >= 2 and s is None:
            s = i
        elif v < 2 and s is not None:
            out.append((s + x0, i - 1 + x0)); s = None
    if s is not None:
        out.append((s + x0, x1 - 1))
    merged = []
    for a_, b_ in out:
        if merged and a_ - merged[-1][1] <= 18:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [int((a_ + b_) / 2) for a_, b_ in merged if b_ - a_ >= minw]


def clip(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


def log_since(size):
    b = open(LOG, "rb").read()[size:]
    t = b.decode("gb18030", errors="replace")
    return [l.strip() for l in t.splitlines() if "setModelVisible" not in l]


# ---- 1) 方案页载入探针想定 ----
click(64, 101, 2.0)
b = segs(20, 620)
print("方案页按钮:", b)
clip(PLAN)
click(b[1], 162, 2.5)
shot("84_dialog.png")
send_keys("%n"); time.sleep(0.5)
send_keys("^a"); time.sleep(0.15)
send_keys("^v"); time.sleep(0.6)
shot("85_typed.png")
send_keys("{ENTER}"); time.sleep(10.0)
shot("86_loaded_probe.png")
raw = open(LOG, "rb").read().decode("gb18030", errors="replace")
tail = [l.strip() for l in raw.splitlines() if "setModelVisible" not in l][-6:]
print("载入后日志:")
for l in tail:
    print("  ", l[:150])

# ---- 2) 仿真页 -> 仿真准备 ----
size = os.path.getsize(LOG)
click(812, 101, 2.0)
b2 = segs(380, 760)
print("仿真页按钮:", b2)
shot("87_sim_page.png")
if b2:
    click(b2[0], 162, 7.0)          # 仿真准备
lines = log_since(size)
print("\n仿真准备后日志（全部新行）:")
for l in lines[-30:]:
    print("  ", l[:180])
shot("88_after_prepare.png")

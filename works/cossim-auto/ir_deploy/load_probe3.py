# -*- coding: utf-8 -*-
"""关闭下拉 -> 确认方案页 -> 打开 -> 载入探针想定。"""
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


def is_plan_page():
    """方案页特征：y≈161 行、x≈500 附近有“上传”文字亮像素"""
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)
    region = a[145:180, 460:540]
    return float((region > 110).mean()) > 0.10


def find_text_button(x0, x1, y0=145, y1=180, thr=110):
    a = np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)
    band = a[y0:y1, x0:x1]
    col = (band > thr).sum(axis=0)
    segs, s = [], None
    for i, v in enumerate(col):
        if v >= 2 and s is None:
            s = i
        elif v < 2 and s is not None:
            segs.append((s + x0, i - 1 + x0)); s = None
    if s is not None:
        segs.append((s + x0, x1 - 1))
    merged = []
    for a_, b_ in segs:
        if merged and a_ - merged[-1][1] <= 18:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [(int((a_ + b_) / 2), int((y0 + y1) / 2)) for a_, b_ in merged if b_ - a_ >= 18]


def clip(text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()


send_keys("{ESC}"); time.sleep(0.8)
click(182, 1013, 2.0)                      # 底部“方案”页签
shot("79_after_switch.png")
print("是否方案页:", is_plan_page())
if not is_plan_page():
    # 尝试点击主视区空白处，再点一次
    click(700, 300, 1.0)
    click(182, 1013, 2.0)
    print("再试后是否方案页:", is_plan_page())
    shot("79b_after_switch2.png")

btns = find_text_button(20, 620, 145, 180)
print("方案页工具栏候选:", btns)
if btns:
    target = None
    for (bx, by) in btns:
        if 150 <= bx <= 210:
            target = (bx, by)
    print("选择“打开”按钮:", target or btns[min(1, len(btns) - 1)])
    bx, by = target or btns[min(1, len(btns) - 1)]
    clip(PLAN)
    click(bx, by, 2.5)
    shot("80_dialog.png")
    send_keys("%n"); time.sleep(0.5)
    send_keys("^a"); time.sleep(0.15)
    send_keys("^v"); time.sleep(0.6)
    shot("81_typed.png")
    send_keys("{ENTER}"); time.sleep(9.0)
    shot("82_loaded.png")
    raw = open(LOG, "rb").read().decode("gb18030", errors="replace")
    lines = [l.strip() for l in raw.splitlines() if "setModelVisible" not in l][-8:]
    print("日志尾部:")
    for l in lines:
        print("  ", l[:150])

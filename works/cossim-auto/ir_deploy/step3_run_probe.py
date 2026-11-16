# -*- coding: utf-8 -*-
"""载入探针想定 -> 仿真准备 -> 抓取日志中与文件/列数有关的报错。"""
import ctypes, os, time
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
PLAN = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\_probe_atmo.xml"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def log_since(size):
    b = open(LOG, "rb").read()[size:]
    t = b.decode("gb18030", errors="replace")
    return [l.strip() for l in t.splitlines() if "setModelVisible" not in l]


size0 = os.path.getsize(LOG)

# 载入探针想定
click(175, 161, 2.0)          # 打开
send_keys("%n"); time.sleep(0.5)
send_keys("^a"); time.sleep(0.1)
send_keys(PLAN, with_spaces=True); time.sleep(0.5)
send_keys("{ENTER}"); time.sleep(9.0)
img = os.path.join(OUT, "70_probe_loaded.png")
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(img)
print("载入后日志:")
for l in log_since(size0)[-8:]:
    print("  ", l[:160])

# 仿真页 -> 仿真准备
size1 = os.path.getsize(LOG)
click(812, 101, 1.5)
click(476, 148, 6.0)
print("\n仿真准备后日志:")
for l in log_since(size1)[-20:]:
    print("  ", l[:180])

ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "71_after_prepare.png"))

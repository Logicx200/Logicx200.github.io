# -*- coding: utf-8 -*-
"""在文件对话框里输入路径并回车，然后截图。"""
import ctypes, os, sys, time
from PIL import ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32
path = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else "07_after_open.png"

# 文件名输入框（绝对坐标）
_u.SetCursorPos(420, 475)
time.sleep(0.2)
_u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.05); _u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.4)
send_keys("^a")
time.sleep(0.1)
send_keys(path, with_spaces=True)
time.sleep(0.4)
send_keys("{ENTER}")
time.sleep(3.0)

ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
print("saved", name)
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
print("--- log tail ---")
for l in lines[-10:]:
    print(l.rstrip())

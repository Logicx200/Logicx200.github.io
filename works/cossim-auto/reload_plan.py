# -*- coding: utf-8 -*-
"""重载想定：点打开 → 双击目标文件 → 截图 + 日志。"""
import ctypes, os, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.5, n=1):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    for _ in range(n):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.05)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.10 if n > 1 else 0.0)
    time.sleep(pause)


click(176, 148, pause=2.0)          # 打开
click(906, 443, pause=6.0, n=2)     # 双击 Anchor_F16_yngd.xml
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "17_reload.png"))
print("saved 17_reload.png")
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
print("--- log tail ---")
for l in lines[-9:]:
    print(l.rstrip())

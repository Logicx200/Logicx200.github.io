# -*- coding: utf-8 -*-
"""双击指定坐标 + 截图 + 日志尾部（UTF-8 正确解码）。"""
import ctypes, sys, time, os
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def double_click(x, y, pause=4.0):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    for _ in range(2):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.05)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.08)
    time.sleep(pause)


if __name__ == "__main__":
    x, y = int(sys.argv[1]), int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "shot.png"
    double_click(x, y)
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    print("--- log tail ---")
    for l in lines[-8:]:
        print(l.rstrip())

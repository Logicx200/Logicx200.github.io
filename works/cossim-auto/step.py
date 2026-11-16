# -*- coding: utf-8 -*-
"""仿真流程单步执行：点击→等待→截图→日志。"""
import ctypes, os, sys, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.05)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))


def tail(n=6):
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return [l.rstrip() for l in lines[-n:]]


if __name__ == "__main__":
    x, y, pause, name = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    click(x, y, pause)
    shot(name)
    print("saved", name)
    print("--- log tail ---")
    for l in tail():
        print(l)

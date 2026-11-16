# -*- coding: utf-8 -*-
"""点击 + 截图 + 打印日志尾部。用法: python act.py X Y 输出名"""
import ctypes, sys, time, os
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.2):
    _u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    _u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(pause)


def tail(path, n=12):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception as e:
        return [f"日志读取失败: {e}"]


if __name__ == "__main__":
    x, y = int(sys.argv[1]), int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "shot.png"
    click(x, y)
    p = os.path.join(OUT, name)
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(p)
    print("saved", p)
    print("--- log tail ---")
    for l in tail(LOG):
        print(l)

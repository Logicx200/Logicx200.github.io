# -*- coding: utf-8 -*-
"""按坐标点击 + 截图（窗口固定 1920x1032）。"""
import ctypes, sys, time, os
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
_user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004


def click(x, y, pause=0.8):
    _user32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(pause)


def shot(name):
    p = os.path.join(OUT, name)
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(p)
    print("saved", p, flush=True)
    return p


if __name__ == "__main__":
    x, y = int(sys.argv[1]), int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "shot.png"
    click(x, y)
    shot(name)

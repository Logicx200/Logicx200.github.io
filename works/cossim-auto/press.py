# -*- coding: utf-8 -*-
"""点击 + 截图 + 打印 GB18030 日志尾部。用法: python press.py X Y 名称 [等待秒]"""
import ctypes, os, sys, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0)


if __name__ == "__main__":
    x, y, name = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    wait = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
    t0 = os.path.getsize(LOG)
    click(x, y)
    time.sleep(wait)
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))
    print("saved", name)
    raw = open(LOG, "rb").read()
    txt = raw.decode("gb18030", errors="replace")
    delta = txt
    # 只打印新增部分中非 setModelVisible 的行
    lines = [l for l in delta.splitlines() if "setModelVisible" not in l][-6:]
    print("--- log tail ---")
    for l in lines:
        print("  ", l.strip()[:150])

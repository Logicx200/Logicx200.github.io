# -*- coding: utf-8 -*-
"""点击仿真准备，抓取大气数据文件相关报错。"""
import ctypes, os, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


size = os.path.getsize(LOG)
click(478, 162, 10.0)
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "92_prepared.png"))
b = open(LOG, "rb").read()[size:]
lines = [l.strip() for l in b.decode("gb18030", errors="replace").splitlines()
         if "setModelVisible" not in l]
print(f"新日志 {len(lines)} 行：")
for l in lines:
    print("  ", l[:200])

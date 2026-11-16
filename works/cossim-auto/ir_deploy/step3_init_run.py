# -*- coding: utf-8 -*-
"""初始化 -> 开始仿真（短时）-> 结束，逐步抓日志中与数据文件/列数有关的报错。"""
import ctypes, os, time
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def read_since(size):
    b = open(LOG, "rb").read()[size:]
    return [l.strip() for l in b.decode("gb18030", errors="replace").splitlines()
            if "setModelVisible" not in l]


def phase(name, x, y, wait):
    size = os.path.getsize(LOG)
    click(x, y, wait)
    lines = read_since(size)
    print(f"\n===== {name}（{len(lines)} 行）=====")
    key = [l for l in lines if any(k in l for k in
           ("错误", "失败", "列数", "无法打开", "大气", "辐射", "透过率", "文件", "WARN", "ERROR"))]
    for l in (key if key else lines)[-20:]:
        print("  ", l[:200])
    return lines


phase("初始化", 617, 162, 8.0)
phase("开始仿真", 760, 162, 6.0)
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "93_running.png"))
phase("结束仿真", 760, 162, 4.0)

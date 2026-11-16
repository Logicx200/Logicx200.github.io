# -*- coding: utf-8 -*-
"""一键：重载想定 → 仿真准备 → 初始化 → 开始仿真 → 等 N 秒 → 结束仿真 → 检查新帧。"""
import ctypes, os, time, glob
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"
_u = ctypes.windll.user32


def click(x, y, pause=1.2, n=1):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    for _ in range(n):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.12 if n > 1 else 0.0)
    time.sleep(pause)


def newest_run():
    dirs = sorted(glob.glob(os.path.join(RT, "ImageData", "*")))
    return dirs[-1] if dirs else None


print("1) 回方案页 + 打开")
click(64, 101, 1.5)
click(176, 148, 2.0)
print("2) 双击想定文件")
click(906, 443, 6.0, n=2)
print("3) 进仿真页")
click(812, 101, 2.0)
print("4) 仿真准备")
click(476, 148, 4.0)
print("5) 初始化")
click(618, 148, 6.0)
print("6) 开始仿真")
click(759, 148, 10.0)
print("7) 结束仿真")
click(759, 148, 3.0)

ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "30_rerun.png"))
run = newest_run()
print("最新输出目录:", run)
if run:
    bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
    print("帧数:", len(bmps))
    for p in (bmps[0], bmps[len(bmps)//2], bmps[-1]) if bmps else []:
        a = np.asarray(Image.open(p).convert("L"))
        print(f"  {os.path.basename(p)}: min={a.min()} max={a.max()} mean={a.mean():.1f} std={a.std():.1f}")
    if bmps:
        Image.open(bmps[len(bmps)//2]).convert("L").save(os.path.join(OUT, "30_frame_mid.png"))
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
print("--- log tail ---")
for l in lines[-6:]:
    print(l.rstrip())

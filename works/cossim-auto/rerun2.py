# -*- coding: utf-8 -*-
"""正确状态机重跑：仿真退出 → 仿真准备 → 初始化 → 开始仿真 → 结束。"""
import ctypes, glob, os, time
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


before = set(glob.glob(os.path.join(RT, "ImageData", "*")))
print("重载想定 ...")
click(64, 101, 1.5)          # 方案页
click(176, 148, 2.0)         # 打开
click(906, 443, 6.0, n=2)    # 双击想定
click(812, 101, 1.5)         # 仿真页

print("仿真退出 → 仿真准备 → 初始化 → 开始")
click(476, 148, 2.5)         # 仿真退出（若已是准备态则是仿真准备）
click(476, 148, 4.0)         # 仿真准备
click(618, 148, 6.0)         # 初始化
click(759, 148, 12.0)        # 开始仿真
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "31_running.png"))
click(759, 148, 3.0)         # 结束仿真
print("已结束")

after = set(glob.glob(os.path.join(RT, "ImageData", "*"))) - before
print("新的输出目录:", after)
for run in sorted(after):
    bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
    print(f"  {os.path.basename(run)}: {len(bmps)} 帧")
    if bmps:
        for p in (bmps[0], bmps[len(bmps)//2], bmps[-1]):
            a = np.asarray(Image.open(p).convert("L"))
            print(f"    {os.path.basename(p)}: min={a.min()} max={a.max()} mean={a.mean():.2f} std={a.std():.2f}")
        Image.open(bmps[len(bmps)//2]).convert("L").save(os.path.join(OUT, "31_frame.png"))
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
print("--- log tail ---")
for l in lines[-8:]:
    print(l.rstrip())

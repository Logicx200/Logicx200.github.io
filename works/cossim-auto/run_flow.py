# -*- coding: utf-8 -*-
"""日志驱动的仿真流程：每步点击后轮询日志关键字确认，再进下一步。"""
import ctypes, glob, os, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"
_u = ctypes.windll.user32


def click(x, y):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.15)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0)


def logsize():
    return os.path.getsize(LOG)


def wait_log(marker, t0_size, timeout=25.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        with open(LOG, "r", encoding="utf-8", errors="replace") as f:
            f.seek(t0_size)
            chunk = f.read()
        if marker in chunk:
            return True, chunk.strip().splitlines()[-1] if chunk.strip() else ""
        time.sleep(0.6)
    return False, "超时"


def step(name, x, y, marker, timeout=25.0):
    t0 = logsize()
    click(x, y)
    ok, line = wait_log(marker, t0, timeout)
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: {line[:120]}")
    return ok


before = set(glob.glob(os.path.join(RT, "ImageData", "*")))
step("仿真准备", 476, 148, "仿真准备指令执行完毕")
step("初始化", 618, 148, "初始化指令执行完毕")
step("开始仿真", 759, 148, "开始仿真指令执行完毕", timeout=30)
time.sleep(8.0)
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "32_run.png"))
step("结束仿真", 759, 148, "结束仿真指令", timeout=20)

after = set(glob.glob(os.path.join(RT, "ImageData", "*"))) - before
print("新输出目录:", after)
for run in sorted(after):
    bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
    print(f"  {os.path.basename(run)}: {len(bmps)} 帧")
    for p in (bmps[0], bmps[len(bmps)//2], bmps[-1]) if bmps else []:
        a = np.asarray(Image.open(p).convert("L"))
        print(f"    {os.path.basename(p)}: min={a.min()} max={a.max()} mean={a.mean():.2f} std={a.std():.2f}")
    if bmps:
        Image.open(bmps[len(bmps)//2]).convert("L").save(os.path.join(OUT, "32_frame.png"))

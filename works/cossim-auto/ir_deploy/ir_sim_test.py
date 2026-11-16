# -*- coding: utf-8 -*-
"""决定性测试：IR 想定短时仿真，只存 2.5 秒图像，检查帧内容后清理。"""
import ctypes, glob, os, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))


def log_tail(n=8):
    raw = open(LOG, "rb").read()
    txt = raw.decode("gb18030", errors="replace")
    return [l.strip() for l in txt.splitlines() if "setModelVisible" not in l][-n:]


before = set(glob.glob(os.path.join(RT, "ImageData", "*")))
click(812, 101, 1.5)          # 仿真页
shot("50_sim_page.png")
click(476, 148, 5.0)          # 仿真准备
print("准备后日志:")
for l in log_tail(3):
    print("  ", l[:130])
click(618, 148, 6.0)          # 初始化
print("初始化后日志:")
for l in log_tail(3):
    print("  ", l[:130])
click(759, 148, 3.0)          # 开始仿真
print("开始后日志:")
for l in log_tail(3):
    print("  ", l[:130])
click(1705, 148, 2.5)         # 存储图像
click(1705, 148, 1.0)         # 停止存储
shot("51_running.png")
click(759, 148, 3.0)          # 结束仿真
print("结束后日志:")
for l in log_tail(3):
    print("  ", l[:130])

after = sorted(set(glob.glob(os.path.join(RT, "ImageData", "*"))) - before)
print("\n新的输出目录:", [os.path.basename(a) for a in after])
for run in after:
    bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
    print(f"{os.path.basename(run)}: {len(bmps)} 帧")
    for p in (bmps[0], bmps[len(bmps) // 2], bmps[-1]) if bmps else []:
        a = np.asarray(Image.open(p).convert("L"))
        print(f"  {os.path.basename(p)}: min={a.min()} max={a.max()} mean={a.mean():.2f} std={a.std():.2f}")
    if bmps:
        Image.open(bmps[len(bmps) // 2]).convert("L").save(os.path.join(OUT, "52_ir_frame.png"))

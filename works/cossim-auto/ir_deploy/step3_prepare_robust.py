# -*- coding: utf-8 -*-
"""稳妥执行：识别当前页 -> 切仿真页 -> 点仿真准备 -> 抓格式报错。"""
import ctypes, os, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32


def click(x, y, pause=2.0):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(n):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, n))


def frame():
    return np.asarray(ImageGrab.grab(all_screens=False).convert("L")).astype(int)


def bright_frac(a, x0, x1, y0=145, y1=180, thr=110):
    return float((a[y0:y1, x0:x1] > thr).mean())


def page_kind():
    a = frame()
    sim_store = bright_frac(a, 1520, 1720)      # 仿真页右侧“存储图像”
    plan_upload = bright_frac(a, 450, 540)      # 方案页“上传”
    if sim_store > 0.08 and plan_upload < 0.08:
        return "sim"
    if plan_upload > 0.06:
        return "plan"
    return "unknown"


def segs(x0, x1, y0=145, y1=180, thr=110, minw=30):
    a = frame()
    band = a[y0:y1, x0:x1]
    col = (band > thr).sum(axis=0)
    out, s = [], None
    for i, v in enumerate(col):
        if v >= 2 and s is None:
            s = i
        elif v < 2 and s is not None:
            out.append((s + x0, i - 1 + x0)); s = None
    if s is not None:
        out.append((s + x0, x1 - 1))
    merged = []
    for a_, b_ in out:
        if merged and a_ - merged[-1][1] <= 18:
            merged[-1] = [merged[-1][0], b_]
        else:
            merged.append([a_, b_])
    return [(int((a_ + b_) / 2), int((y0 + y1) / 2), b_ - a_)
            for a_, b_ in merged if b_ - a_ >= minw]


def log_since(size):
    b = open(LOG, "rb").read()[size:]
    return [l.strip() for l in b.decode("gb18030", errors="replace").splitlines()
            if "setModelVisible" not in l]


print("当前页:", page_kind())
for attempt in range(3):
    if page_kind() == "sim":
        break
    click(812, 101, 2.5)
    print(f"切仿真页尝试 {attempt + 1}: {page_kind()}")
shot("90_sim_page.png")
b = segs(380, 1000)
print("仿真页按钮段:", b)

# 仿真页四个按钮：取宽度>=60 的前 4 个段
buttons = [x for x in b if x[2] >= 55][:4]
print("候选四按钮:", buttons)
if buttons and page_kind() == "sim":
    size = os.path.getsize(LOG)
    click(buttons[0][0], buttons[0][1], 8.0)
    shot("91_after_prepare.png")
    lines = log_since(size)
    print(f"\n新日志 {len(lines)} 行，尾部:")
    for l in lines[-25:]:
        print("  ", l[:180])

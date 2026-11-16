# -*- coding: utf-8 -*-
"""抓取可见光预览窗，自动定位 1024x768 渲染区并统计。"""
import os
import numpy as np
import psutil, win32gui, win32process
from PIL import ImageGrab, Image

OUT = r"F:\DeepSeek工作区\_cossim_auto\geom"
os.makedirs(OUT, exist_ok=True)

pid = next(p.info["pid"] for p in psutil.process_iter(["pid", "name"])
           if "XGCOSSim" in (p.info["name"] or ""))
target = None


def cb(h, _):
    global target
    try:
        _, wp = win32process.GetWindowThreadProcessId(h)
        if wp == pid and win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            if t and "仿真软件" not in t:
                target = (h, t, win32gui.GetWindowRect(h))
    except Exception:
        pass
    return True


win32gui.EnumWindows(cb, None)
print("预览窗:", target)
h, title, rect = target
x0, y0, x1, y1 = rect
win = ImageGrab.grab(bbox=(rect[0], rect[1], rect[2], rect[3]))
win.save(os.path.join(OUT, "01_preview_window.png"))
print("窗口截图:", win.size)

a = np.asarray(win.convert("L")).astype(float)
H, W = a.shape
# 渲染区通常是窗口内最大的一块"内容丰富"矩形：按行列标准差找边界
row_std = a.std(axis=1)
col_std = a.std(axis=0)
rows = np.where(row_std > 8)[0]
cols = np.where(col_std > 8)[0]
print("行范围:", rows.min(), rows.max(), " 列范围:", cols.min(), cols.max())

# 更稳的做法：找连续的大块区域
def longest_run(mask):
    best = (0, -1, 0)
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i - 1, i - start)
            start = None
    if start is not None and len(mask) - start > best[1] - best[0]:
        best = (start, len(mask) - 1, len(mask) - start)
    return best

r0, r1, rh = longest_run(row_std > 6)
c0, c1, cw = longest_run(col_std > 6)
print(f"连续区域: rows {r0}-{r1} ({rh}), cols {c0}-{c1} ({cw}), 宽高比={cw/rh:.4f}")
crop = win.crop((c0, r0, c1 + 1, r1 + 1))
crop.save(os.path.join(OUT, "02_render_area_raw.png"))
print("渲染区候选:", crop.size, " 1024/768 =", 1024/768)

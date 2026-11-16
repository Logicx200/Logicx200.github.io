# -*- coding: utf-8 -*-
"""枚举 XGCOSSim 的顶层窗口（含预览窗），截图并统计像素。"""
import os
import numpy as np
import psutil, win32gui, win32process
from PIL import ImageGrab, Image

OUT = r"F:\DeepSeek工作区\_cossim_auto"
pid = next(p.info["pid"] for p in psutil.process_iter(["pid", "name"])
           if "XGCOSSim" in (p.info["name"] or ""))
wins = []


def cb(h, _):
    try:
        _, wpid = win32process.GetWindowThreadProcessId(h)
        if wpid == pid and win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h)
            cls = win32gui.GetClassName(h)
            r = win32gui.GetWindowRect(h)
            if r[2] - r[0] > 80 and r[3] - r[1] > 80:
                wins.append((h, cls, t, r))
    except Exception:
        pass
    return True


win32gui.EnumWindows(cb, None)
print("可见窗口:", len(wins))
for h, cls, t, r in wins:
    print(f"  hwnd={h} class={cls!r} title={t!r} rect={r} size={r[2]-r[0]}x{r[3]-r[1]}")

# 找预览窗（有标题且不是主窗口）
prev = [w for w in wins if w[2] and "仿真软件" not in w[2]]
for h, cls, t, r in prev:
    x0, y0, x1, y1 = r
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, 1920), min(y1, 1080)
    img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
    name = f"preview_{t[:12].replace(' ', '_')}.png"
    img.save(os.path.join(OUT, name))
    a = np.asarray(img.convert("L"))
    print(f"\n预览窗 {t!r}: {img.size} min={a.min()} max={a.max()} mean={a.mean():.1f} "
          f"std={a.std():.1f} 非零像素比={(a > 5).mean()*100:.1f}% -> {name}")

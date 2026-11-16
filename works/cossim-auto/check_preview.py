# -*- coding: utf-8 -*-
"""切回方案页，选中传感器节点，抓预览窗并统计。"""
import ctypes, os, time
import numpy as np
import psutil, win32gui, win32process
from PIL import ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto"
_u = ctypes.windll.user32


def click(x, y, pause=1.2, n=1):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    for _ in range(n):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.15 if n > 1 else 0.0)
    time.sleep(pause)


def dump_windows(tag):
    pid = next(p.info["pid"] for p in psutil.process_iter(["pid", "name"])
               if "XGCOSSim" in (p.info["name"] or ""))
    wins = []

    def cb(h, _):
        try:
            _, wp = win32process.GetWindowThreadProcessId(h)
            if wp == pid and win32gui.IsWindowVisible(h):
                r = win32gui.GetWindowRect(h)
                if r[2] - r[0] > 80 and r[3] - r[1] > 80:
                    wins.append((h, win32gui.GetWindowText(h), r))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    print(f"--- {tag}: {len(wins)} 个窗口 ---")
    for h, t, r in wins:
        print(f"    {t!r} rect={r} size={r[2]-r[0]}x{r[3]-r[1]}")
        if t and "仿真软件" not in t:
            x0, y0 = max(r[0], 0), max(r[1], 0)
            x1, y1 = min(r[2], 1920), min(r[3], 1080)
            img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            fn = os.path.join(OUT, f"52_preview_{tag}.png")
            img.save(fn)
            a = np.asarray(img.convert("L"))
            print(f"      -> {os.path.basename(fn)} min={a.min()} max={a.max()} "
                  f"mean={a.mean():.1f} std={a.std():.1f} 非零={(a>5).mean()*100:.1f}%")


click(182, 1013, 1.5)                 # 方案 tab（左下切换）
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "52_fangan.png"))
print("saved 52_fangan.png")
dump_windows("current")

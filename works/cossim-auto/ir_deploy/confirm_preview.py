# -*- coding: utf-8 -*-
"""配置页双击可见光传感器，确认预览窗打开方式。"""
import ctypes, os, time
import numpy as np
import psutil, win32gui, win32process
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=1.5, n=1):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    for _ in range(n):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.18 if n > 1 else 0.0)
    time.sleep(pause)


def dump(tag):
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
    print(f"--- {tag}: {len(wins)} 窗口 ---")
    for h, t, r in wins:
        print(f"  {t!r} {r[2]-r[0]}x{r[3]-r[1]}")
        if t and "仿真软件" not in t:
            x0, y0 = max(r[0], 0), max(r[1], 0)
            x1, y1 = min(r[2], 1920), min(r[3], 1080)
            fn = os.path.join(OUT, f"36_prev_{tag}.png")
            ImageGrab.grab(bbox=(x0, y0, x1, y1)).save(fn)
            a = np.asarray(Image.open(fn).convert("L"))
            print(f"     -> {os.path.basename(fn)} min={a.min()} max={a.max()} "
                  f"mean={a.mean():.1f} std={a.std():.1f}")


click(27, 1013, 1.5)                  # 配置
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "36_config.png"))
# 配置树中：传感器/可见光/可见光传感器 在下方，先滚动/直接按坐标点
# 从 32_tree_zoom 推算：整树截图区域 (0,180)-(330,1032)；
# 传感器 header 约 abs y=800；可见光 y=830；可见光传感器 y=860
for y in (860, 866):
    click(120, y, 2.5, n=2)
    dump(f"dbl_{y}")
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "36_after_dbl.png"))
print("saved 36_after_dbl.png")

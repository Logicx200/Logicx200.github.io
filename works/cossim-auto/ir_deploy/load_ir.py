# -*- coding: utf-8 -*-
"""在已运行的 XGCOSSim 中载入 IR 想定并截图。"""
import ctypes, os, time
import numpy as np
import psutil, win32gui, win32process
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PLAN = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\Anchor_F16_yngd_IR.xml"
_u = ctypes.windll.user32


def shot(name):
    p = os.path.join(OUT, name)
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(p)
    print("saved", name, flush=True)
    return p


def click(x, y, pause=1.0, n=1):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    for _ in range(n):
        _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
        _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(0.12 if n > 1 else 0.0)
    time.sleep(pause)


def toolbar_buttons(img_path, y0=118, y1=185):
    im = np.asarray(Image.open(img_path).convert("L")).astype(int)
    band = im[y0:y1]
    col = (band > 120).sum(axis=0)
    segs, s = [], None
    for x, v in enumerate(col):
        if v >= 2 and s is None:
            s = x
        elif v < 2 and s is not None:
            segs.append((s, x - 1)); s = None
    if s is not None:
        segs.append((s, len(col) - 1))
    merged = []
    for a, b in segs:
        if merged and a - merged[-1][1] <= 22:
            merged[-1] = [merged[-1][0], b]
        else:
            merged.append([a, b])
    return [(int((a + b) / 2), int((y0 + y1) / 2)) for a, b in merged]


shot("23_before_open.png")
btns = toolbar_buttons(os.path.join(OUT, "23_before_open.png"))
print("工具栏按钮:", btns[:6])
if len(btns) >= 2:
    click(btns[1][0], btns[1][1], 2.5)          # 打开
    shot("24_dialog.png")
    send_keys("%n"); time.sleep(0.5)
    send_keys("^a"); time.sleep(0.1)
    send_keys(PLAN, with_spaces=True); time.sleep(0.6)
    send_keys("{ENTER}"); time.sleep(9.0)
    shot("25_loaded.png")

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
print("\n窗口列表:")
for h, t, r in wins:
    print(f"  {t!r} {r[2]-r[0]}x{r[3]-r[1]}")
    if t and "仿真软件" not in t:
        x0, y0 = max(r[0], 0), max(r[1], 0)
        x1, y1 = min(r[2], 1920), min(r[3], 1080)
        fn = os.path.join(OUT, "26_preview.png")
        ImageGrab.grab(bbox=(x0, y0, x1, y1)).save(fn)
        a = np.asarray(Image.open(fn).convert("L"))
        print(f"     -> 26_preview.png min={a.min()} max={a.max()} mean={a.mean():.1f} std={a.std():.1f}")

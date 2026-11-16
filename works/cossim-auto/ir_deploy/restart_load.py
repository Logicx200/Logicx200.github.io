# -*- coding: utf-8 -*-
"""重启 XGCOSSim -> 载入 IR 想定 -> 截图并枚举预览窗。"""
import ctypes, os, subprocess, time
import numpy as np
import psutil, win32gui, win32process
from PIL import Image, ImageGrab
from pywinauto.keyboard import send_keys

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
EXE = r"D:\XGGDCOSSim2\bin\XGCOSSimDesktop.exe"
WD = r"D:\XGGDCOSSim2\bin"
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


def find_toolbar_buttons(img_path, y0=118, y1=185):
    im = np.asarray(Image.open(img_path).convert("L")).astype(int)
    band = im[y0:y1]
    bright = band > 120
    col = bright.sum(axis=0)
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


# 1) 关闭
for p in psutil.process_iter(["pid", "name"]):
    if "XGCOSSim" in (p.info["name"] or ""):
        try:
            p.terminate(); print("已终止 PID", p.info["pid"])
        except Exception as e:
            print("终止失败", e)
time.sleep(3)

# 2) 启动
proc = subprocess.Popen([EXE], cwd=WD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("启动 PID", proc.pid, flush=True)
t0 = time.time()
main = None
while time.time() - t0 < 90:
    for p in psutil.process_iter(["pid", "name"]):
        if "XGCOSSim" in (p.info["name"] or ""):
            wins = []

            def cb(h, _):
                try:
                    _, wp = win32process.GetWindowThreadProcessId(h)
                    if wp == p.info["pid"] and win32gui.IsWindowVisible(h):
                        r = win32gui.GetWindowRect(h)
                        if r[2] - r[0] > 800:
                            wins.append((h, win32gui.GetWindowText(h)))
                except Exception:
                    pass
                return True
            win32gui.EnumWindows(cb, None)
            if wins:
                main = wins[0]
                break
    if main:
        break
    time.sleep(1)
print("主窗口:", main, "等待 %.1fs" % (time.time() - t0))
time.sleep(4)
shot("20_restarted.png")

# 3) 点“打开”
btns = find_toolbar_buttons(os.path.join(OUT, "20_restarted.png"))
print("工具栏按钮坐标:", btns[:6])
if len(btns) >= 2:
    click(btns[1][0], btns[1][1], 2.5)
    shot("21_open_dialog.png")
    # Alt+N 聚焦文件名，输入完整路径
    send_keys("%n"); time.sleep(0.4)
    send_keys("^a"); time.sleep(0.1)
    send_keys(PLAN, with_spaces=True); time.sleep(0.5)
    send_keys("{ENTER}"); time.sleep(8.0)
    shot("22_loaded_ir.png")
else:
    print("未识别到工具栏按钮")

# 4) 枚举窗口
pid = next(p.info["pid"] for p in psutil.process_iter(["pid", "name"])
           if "XGCOSSim" in (p.info["name"] or ""))
wins = []


def cb2(h, _):
    try:
        _, wp = win32process.GetWindowThreadProcessId(h)
        if wp == pid and win32gui.IsWindowVisible(h):
            r = win32gui.GetWindowRect(h)
            if r[2] - r[0] > 80 and r[3] - r[1] > 80:
                wins.append((h, win32gui.GetWindowText(h), r))
    except Exception:
        pass
    return True


win32gui.EnumWindows(cb2, None)
print("\n当前窗口:")
for h, t, r in wins:
    print(f"  {t!r} {r[2]-r[0]}x{r[3]-r[1]}")

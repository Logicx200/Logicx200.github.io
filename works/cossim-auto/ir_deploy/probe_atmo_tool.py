# -*- coding: utf-8 -*-
"""探测 制备页 -> 大气模型 工具行为（是否弹窗/生成模板）。"""
import ctypes, os, time
import psutil, win32gui, win32process
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
_u = ctypes.windll.user32


def click(x, y, pause=1.5):
    _u.SetCursorPos(int(x), int(y)); time.sleep(0.2)
    _u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
    _u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(pause)


def shot(name):
    ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, name))


def dump(tag):
    pid = next(p.info["pid"] for p in psutil.process_iter(["pid", "name"])
               if "XGCOSSim" in (p.info["name"] or ""))
    wins = []

    def cb(h, _):
        try:
            _, wp = win32process.GetWindowThreadProcessId(h)
            if wp == pid and win32gui.IsWindowVisible(h):
                r = win32gui.GetWindowRect(h)
                wins.append((h, win32gui.GetWindowText(h), r))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    print(f"--- {tag}: {len(wins)} ---")
    for h, t, r in wins:
        print(f"  {t!r} {r}")


# 进制备页
click(900, 101, 2.0)
shot("60_prepare.png")
# 先选中树里的“大气”节点（位置：大气 at abs y≈352? 从早前截图：大气 preview y=329 -> abs 352）
click(60, 352, 1.2)
shot("61_select_atmo_node.png")
dump("after_select")
# 点大气模型按钮（制备页第 4 个按钮 abs x≈491）
click(491, 155, 3.0)
shot("62_atmo_tool.png")
dump("after_tool")

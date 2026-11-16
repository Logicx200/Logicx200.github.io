# -*- coding: utf-8 -*-
"""探测 XGCOSSim 主窗口控件树（先枚举窗口，再按 pid 连接）。"""
import sys, time
import psutil
from pywinauto import Application, Desktop

OUT = r"F:\DeepSeek工作区\_cossim_auto"

procs = [p for p in psutil.process_iter(["pid", "name"]) if "XGCOSSim" in (p.info["name"] or "")]
print("进程:", procs)
pid = procs[0].info["pid"] if procs else None
if pid is None:
    sys.exit("未找到 XGCOSSimDesktop 进程")

desk = Desktop(backend="uia")
cands = []
for w in desk.windows():
    try:
        if w.process_id() == pid:
            cands.append(w)
    except Exception:
        pass
print("该进程窗口数:", len(cands))
for w in cands:
    r = w.rectangle()
    print(f"  {w.window_text()[:40]!r} class={w.class_name()!r} rect={r}")

if not cands:
    sys.exit("没有 UIA 可见窗口")
win = max(cands, key=lambda w: w.rectangle().width() * w.rectangle().height())
print("选中:", win.window_text(), win.rectangle())

rows = []
for c in win.descendants():
    try:
        r = c.rectangle()
        rows.append((c.control_type(), (c.window_text() or "").replace("\n", " "), r.left, r.top, r.width(), r.height()))
    except Exception:
        pass
print("descendants:", len(rows))
with open(OUT + r"\ui_dump.txt", "w", encoding="utf-8") as f:
    for r in rows:
        f.write("\t".join(str(x) for x in r) + "\n")

kinds = {"Button", "TabItem", "MenuItem", "TreeItem", "ListItem", "Text", "ComboBox", "Edit", "CheckBox", "RadioButton"}
shown = [r for r in rows if r[0] in kinds and r[1].strip()]
print("具名控件:", len(shown))
for r in shown[:150]:
    print(f"{r[0]:<10}|{r[1][:44]:<46}|({r[2]},{r[3]},{r[4]}x{r[5]})")
print("saved:", OUT + r"\ui_dump.txt")

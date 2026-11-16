# -*- coding: utf-8 -*-
"""收尾：结束仿真、留存证据、清理大文件。"""
import ctypes, glob, os, shutil, time
import numpy as np
from PIL import Image, ImageGrab

OUT = r"F:\DeepSeek工作区\_cossim_auto\cossim_out"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"
LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
_u = ctypes.windll.user32
os.makedirs(OUT, exist_ok=True)

# 1) 结束仿真
_u.SetCursorPos(759, 148); time.sleep(0.2)
_u.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06)
_u.mouse_event(0x0004, 0, 0, 0, 0); time.sleep(3.0)
ImageGrab.grab(all_screens=False).crop((0, 0, 1920, 1032)).save(os.path.join(OUT, "final_ui.png"))

# 2) 留存证据：帧样本 + 遥测 CSV + 关键日志
runs = sorted(glob.glob(os.path.join(RT, "ImageData", "*")))
print("输出目录:", [os.path.basename(r) for r in runs])
for run in runs[-1:]:
    bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
    if bmps:
        for tag, p in (("first", bmps[0]), ("last", bmps[-1])):
            im = Image.open(p)
            im.save(os.path.join(OUT, f"frame_{tag}.bmp"))
            im.convert("L").save(os.path.join(OUT, f"frame_{tag}.png"))
            a = np.asarray(im.convert("L"))
            print(f"  留存 {tag}: {os.path.basename(p)} max={a.max()} mean={a.mean():.2f}")
csvs = sorted(glob.glob(os.path.join(RT, "CsvData", "*.csv")), key=os.path.getmtime)
if csvs:
    shutil.copy(csvs[-1], os.path.join(OUT, "telemetry_last.csv"))
    with open(csvs[-1], "rb") as f:
        raw = f.read()
    txt = raw.decode("gb18030", errors="replace")
    lines = txt.splitlines()
    with open(os.path.join(OUT, "telemetry_last_utf8.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines[:200]))
    print("  遥测行数:", len(lines), "->", os.path.basename(csvs[-1]))

# 3) 释放磁盘：删除大帧目录（保留 CsvData）
freed = 0
for run in runs:
    for p in glob.glob(os.path.join(run, "*.bmp")):
        try:
            freed += os.path.getsize(p); os.remove(p)
        except OSError:
            pass
print(f"已删除帧文件，释放 {freed/1024/1024:.0f} MB")
print("剩余 ImageData 目录:", [os.path.basename(r) for r in glob.glob(os.path.join(RT, "ImageData", "*"))])

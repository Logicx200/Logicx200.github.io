# -*- coding: utf-8 -*-
"""检查 COSSIM 实时输出：帧图像统计 + 遥测 CSV 结构。"""
import os, shutil
import numpy as np
from PIL import Image

SRC = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"
RUN = "20261103_224552"
img_dir = os.path.join(SRC, "ImageData", RUN)
OUT = r"F:\DeepSeek工作区\_cossim_auto\cossim_out"
os.makedirs(OUT, exist_ok=True)

files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(".bmp")],
               key=lambda s: int(s.split(".")[0]))
print("帧文件数:", len(files), "首/尾:", files[0], files[-1])

for name in (files[0], files[len(files)//2], files[-1]):
    p = os.path.join(img_dir, name)
    im = Image.open(p)
    a = np.asarray(im)
    print(f"{name}: mode={im.mode} size={im.size} dtype={a.dtype} "
          f"min={a.min()} max={a.max()} mean={a.mean():.2f} std={a.std():.2f} "
          f"unique={len(np.unique(a))}")
    if a.ndim == 3:
        gray = a[..., 0]
        print(f"   R 通道: min={gray.min()} max={gray.max()} mean={gray.mean():.1f}")

# 复制首/中/尾帧为 png 便于查看
for tag, name in (("first", files[0]), ("mid", files[len(files)//2]), ("last", files[-1])):
    im = Image.open(os.path.join(img_dir, name)).convert("L")
    im.save(os.path.join(OUT, f"frame_{tag}.png"))
print("saved frames to", OUT)

# 遥测 CSV
csv = os.path.join(SRC, "CsvData", RUN + ".csv")
print("\nCSV:", csv, os.path.getsize(csv), "bytes")
with open(csv, "r", encoding="utf-8-sig", errors="replace") as f:
    head = [next(f).rstrip("\n") for _ in range(6)]
for h in head:
    print("  ", h[:300])
shutil.copy(csv, os.path.join(OUT, "telemetry.csv"))
axis = os.path.join(SRC, "ImageData", RUN, "AxisData.csv")
if os.path.exists(axis):
    print("\nAxisData.csv:")
    with open(axis, "r", encoding="utf-8-sig", errors="replace") as f:
        for i, l in enumerate(f):
            if i > 5: break
            print("  ", l.rstrip()[:300])

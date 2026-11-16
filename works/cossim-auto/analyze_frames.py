# -*- coding: utf-8 -*-
"""分析最新一轮 COSSIM 输出帧。"""
import glob, os
import numpy as np
from PIL import Image

RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData\ImageData"
OUT = r"F:\DeepSeek工作区\_cossim_auto"
run = sorted(glob.glob(os.path.join(RT, "*")))[-1]
bmps = sorted(glob.glob(os.path.join(run, "*.bmp")), key=lambda p: int(os.path.basename(p).split(".")[0]))
print("run:", os.path.basename(run), "帧数:", len(bmps))
for p in (bmps[0], bmps[len(bmps)//4], bmps[len(bmps)//2], bmps[-1]):
    im = Image.open(p)
    a = np.asarray(im)
    g = a[..., 0] if a.ndim == 3 else a
    print(f"  {os.path.basename(p)}: {im.mode} {im.size} min={g.min()} max={g.max()} "
          f"mean={g.mean():.2f} std={g.std():.2f} unique={len(np.unique(g))}")
best = max(bmps, key=lambda p: np.asarray(Image.open(p).convert("L")).std())
print("对比度最高帧:", os.path.basename(best))
Image.open(best).convert("L").save(os.path.join(OUT, "46_best_frame.png"))
Image.open(bmps[len(bmps)//2]).convert("L").save(os.path.join(OUT, "46_mid_frame.png"))
print("saved 46_best_frame.png / 46_mid_frame.png")

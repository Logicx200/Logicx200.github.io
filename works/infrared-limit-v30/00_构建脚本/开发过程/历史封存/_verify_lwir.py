# -*- coding: utf-8 -*-
"""核对：当前磁盘 npz 的 LWIR 组成 vs 实验长表中实际使用的 LWIR 透过率。"""
import os
import sys

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))
import numpy as np
import pandas as pd
import irrecog.atmosphere as A

p = os.path.join(ROOT, "07_光谱数据", "xsect_lwir.npz")
print("npz size:", os.path.getsize(p), "mtime:", os.path.getmtime(p))
lam, species, temps, src = A._xsect_band_grid("LWIR")
print("LWIR species:", list(species), "temps:", temps)
print("source:", src)

at = A.Atmo()
for r in (1.0, 10.0, 20.0):
    st = A.spectral_state(at, "LWIR", r, 0.0, 8000.0)
    print(f"当前模型 LWIR {r:5.1f} km tau={st['tau_band']:.6f}")

# 长表中 S02 的 LWIR 基线透过率
lp = os.path.join(ROOT, "03_数据", "全工况长表", "eval_long.csv.gz")
df = pd.read_csv(lp, encoding="utf-8-sig", low_memory=False)
sub = df[(df["sweep_id"] == "S02") & (df["band"] == "LWIR") & (df["target"] == "F16")]
for r in (1.0, 10.0, 20.0):
    row = sub.iloc[(sub["r_ground_km"] - r).abs().argmin()]
    print(f"长表 LWIR F16 {r:5.1f} km tau={row['tau_band']:.6f}  (r={row['r_ground_km']:.2f})")

# MWIR 对照
for r in (1.0, 10.0, 20.0):
    st = A.spectral_state(at, "MWIR", r, 0.0, 8000.0)
    print(f"当前模型 MWIR {r:5.1f} km tau={st['tau_band']:.6f}")

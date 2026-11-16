# -*- coding: utf-8 -*-
"""最终口径的轻量验证：临界状态(0.5R50 + 10km 附列) 与 波段对比（F16 小样本）。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import numpy as np
import pandas as pd

from irrecog import chain, experiments as E

TMP = os.path.join(ROOT, "00_构建脚本", "开发过程", "_smoke2")
os.makedirs(TMP, exist_ok=True)

t0 = time.time()
chain.evaluate(chain.baseline_scenario(), 10.0)
print(f"[timing] 单点冷评估 {(time.time()-t0)*1000:.1f} ms")
t0 = time.time()
for r in (11.0, 12.0, 13.0, 14.0, 15.0):
    chain.evaluate(chain.baseline_scenario(), r)
print(f"[timing] 5 个新距离评估 {(time.time()-t0):.2f} s "
      f"(平均 {(time.time()-t0)/5*1000:.1f} ms)")

print("\n=== 临界状态（新口径 r_ref=0.5R50）===")
t0 = time.time()
crit = E.run_critical_states(TMP, verbose=True)
print(f"[timing] 临界状态全部 6 目标 {(time.time()-t0):.1f} s")
show = [c for c in ["target", "R50_ground_km", "r_ref_km", "AOD_crit", "Cn2_crit",
                    "dT_blind_low_K", "dT_blind_high_K", "dT_blind_width_K",
                    "dT_blind_width_10km", "D_crit", "NETD_crit",
                    "R_contrast_floor_km", "censored_AOD", "censored_dT"] if c in crit.columns]
print(crit[show].to_string(index=False))

print("\n=== 波段对比（F16 小样本）===")
t0 = time.time()
band = E.run_band_compare(TMP, targets=["F16"], verbose=False)
print(f"[timing] 波段对比 F16 {(time.time()-t0):.1f} s, {len(band)} 行")
print(band[["band", "aod550", "pwv_cm", "R50_ground_km", "R90", "R_res", "eta"]].head(6).to_string(index=False))
print("...")
print(band[["band", "aod550", "pwv_cm", "R50_ground_km", "R90", "R_res", "eta"]].tail(4).to_string(index=False))
print("\n完成")

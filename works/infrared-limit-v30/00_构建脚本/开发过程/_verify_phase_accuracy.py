# -*- coding: utf-8 -*-
"""相图求解精度校核：相图(粗网格+共享细化) vs critical.range_summary(完整二分)。

注意：必须用完全相同的网格值（不能 np.isclose 默认 atol 匹配小量），
因此这里直接取 PHASE_AOD/PHASE_CN2 网格的子集索引。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import numpy as np
import pandas as pd

from irrecog import chain, critical, experiments as E

BASE = chain.baseline_scenario()
print("== 0) 快速通道一致性（当前 atmosphere） ==", flush=True)
print(" ", critical.validate_fast_path(8, verbose=True), flush=True)

OUT = os.path.join(ROOT, "00_构建脚本", "开发过程", "_phase_acc")
os.makedirs(os.path.join(OUT, "相图"), exist_ok=True)

# ---- 相图 1：AOD × Cn²（F16，网格子集：5 AOD × 6 Cn²） ----
ia = [0, 6, 12, 18, 24]
ic = [0, 4, 8, 12, 16, 20]
sub_aod = E.PHASE_AOD[ia]
sub_cn2 = E.PHASE_CN2[ic]
keep = (E.PHASE_AOD, E.PHASE_CN2, E.PHASE_TARGETS)
E.PHASE_AOD = sub_aod
E.PHASE_CN2 = sub_cn2
E.PHASE_TARGETS = ("F16",)
t0 = time.time()
df1 = E._phase_aod_cn2(OUT, verbose=False)
t_phase1 = time.time() - t0
E.PHASE_AOD, E.PHASE_CN2, E.PHASE_TARGETS = keep
print(f"\n== 1a) AOD×Cn² 相图子集：{len(df1)} 格，耗时 {t_phase1:.1f}s ==", flush=True)
worst = (0.0, None)
n_cmp = 0
for aod in sub_aod:
    for cn2 in sub_cn2:
        scn = BASE.with_(target_key="F16", aod550=float(aod), cn2=float(cn2))
        ref = critical.range_summary(scn, specs=(("R50", "recognize", 0.5),))["R50"]["r_km"]
        row = df1[(np.isclose(df1["aod550"], aod, rtol=1e-9, atol=0.0))
                  & (np.isclose(df1["cn2"], cn2, rtol=1e-9, atol=0.0))]
        v = float(row["R50"].iloc[0]) if len(row) else float("nan")
        if np.isfinite(ref) and np.isfinite(v):
            rel = abs(v - ref) / ref
            n_cmp += 1
            if rel > worst[0]:
                worst = (rel, (aod, cn2, v, ref))
            print(f"  AOD={aod:7.4g} Cn2={cn2:.4g}: phase={v:8.4f} bisect={ref:8.4f} rel={rel:.3%}", flush=True)
        else:
            print(f"  AOD={aod:7.4g} Cn2={cn2:.4g}: phase={v} bisect={ref} (censored/NaN)", flush=True)
print(f"  比较 {n_cmp} 格，最大相对差 = {worst[0]:.3%}  详情={worst[1]}", flush=True)

# ---- 相图 2：ΔT × AOD（F16，网格子集：4 AOD × 5 ΔT） ----
ia2 = [0, 7, 14, 20]
idt = [0, 5, 9, 14, 20, 25]   # 含 -0.1/0/0.1 附近的不可识别行
sub_aod2 = E.PHASE_AOD_DT[ia2]
sub_dt = E.PHASE_DT[idt]
keep2 = (E.PHASE_AOD_DT, E.PHASE_DT)
E.PHASE_AOD_DT = sub_aod2
E.PHASE_DT = sub_dt
t0 = time.time()
df2 = E._phase_dt_aod(OUT, verbose=False)
t_phase2 = time.time() - t0
E.PHASE_AOD_DT, E.PHASE_DT = keep2
print(f"\n== 2a) ΔT×AOD 相图子集：{len(df2)} 格，耗时 {t_phase2:.1f}s ==", flush=True)
worst2 = (0.0, None)
n_cmp2 = 0
for aod in sub_aod2:
    for dt in sub_dt:
        scn = BASE.with_(target_key="F16", aod550=float(aod),
                         target_temp_c=float(BASE.bg_temp_c + dt))
        ref = critical.range_summary(scn, specs=(("R50", "recognize", 0.5),))["R50"]["r_km"]
        row = df2[(np.isclose(df2["aod550"], aod, rtol=1e-9, atol=0.0))
                  & (np.isclose(df2["dT_K"], dt, rtol=1e-9, atol=0.0))]
        v = float(row["R50"].iloc[0]) if len(row) else float("nan")
        if np.isfinite(ref) and np.isfinite(v):
            rel = abs(v - ref) / ref
            n_cmp2 += 1
            if rel > worst2[0]:
                worst2 = (rel, (aod, dt, v, ref))
            print(f"  AOD={aod:7.4g} dT={dt:+6.2f}: phase={v:8.4f} bisect={ref:8.4f} rel={rel:.3%}", flush=True)
        else:
            print(f"  AOD={aod:7.4g} dT={dt:+6.2f}: phase={v} bisect={ref} (censored/NaN)", flush=True)
print(f"  比较 {n_cmp2} 格，最大相对差 = {worst2[0]:.3%}  详情={worst2[1]}", flush=True)
print("\n完成")

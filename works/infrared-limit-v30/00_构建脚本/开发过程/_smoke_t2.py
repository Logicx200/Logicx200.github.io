# -*- coding: utf-8 -*-
"""T2 内部冒烟测试：求解器精度 + 新 experiments 各数据产品（小样本，输出到临时目录）。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import numpy as np
import pandas as pd

from irrecog import chain, critical, experiments as E

OUT = os.path.join(ROOT, "00_构建脚本", "开发过程", "_smoke_data")
os.makedirs(OUT, exist_ok=True)


def sec(tag, fn, *a, **kw):
    t = time.time()
    out = fn(*a, **kw)
    print(f"[smoke] {tag}: {time.time()-t:.1f}s", flush=True)
    return out


base = chain.baseline_scenario()
print("[smoke] validate_fast_path:", critical.validate_fast_path(8, verbose=True), flush=True)
print("[smoke] R50 baseline =", critical.r50(base), flush=True)

# --- 1) 15 组 OFAT 的 2 组（S01/S02） ---
res = sec("run_all(S01,S02, targets=F16)", E.run_all, OUT, targets=["F16"],
          sweep_ids=["S01", "S02"], with_band=False, with_phase=False)
print("[smoke] long rows =", len(res["long"]), "summary rows =", len(res["summary"]), flush=True)
print("[smoke] long cols =", list(res["long"].columns)[:5], "...", list(res["long"].columns)[-3:], flush=True)
print(res["summary"][["sweep_id", "target", "band", "R50_ground_km", "R90_ground_km",
                      "R_res_analytic_km", "eta", "censored"]].to_string(), flush=True)

# --- 2) 环境工况（1 个目标） ---
env = sec("run_environments(targets=F16)", E.run_environments, OUT, targets=["F16"], verbose=False)
print("[smoke] env rows =", len(env), "cols =", list(env.columns), flush=True)

# --- 3) 临界状态（1 个目标，2 个目标看盲区） ---
crit = sec("run_critical_states(F16,HM)", E.run_critical_states, OUT, targets=["F16", "HM"], verbose=True)
print(crit.T.to_string(), flush=True)

# --- 4) 波段对比（1 个目标） ---
band = sec("run_band_compare(F16)", E.run_band_compare, OUT, targets=["F16"], verbose=False)
print("[smoke] band rows =", len(band), "cols =", list(band.columns), flush=True)
print(band[["band", "aod550", "pwv_cm", "R50_ground_km", "R90", "R_res", "eta"]].head(25).to_string(), flush=True)

# --- 5) 相图（缩减网格） ---
E.PHASE_AOD = E.PHASE_AOD[:3]
E.PHASE_CN2 = E.PHASE_CN2[:3]
E.PHASE_TARGETS = ("F16",)
E.PHASE_AOD_DT = E.PHASE_AOD_DT[:2]
E.PHASE_DT = np.array([-2.0, -0.2, 0.0, 0.2, 2.0, 10.0])
E.PHASE_ROUNDS = 1
ph = sec("run_phase_maps(reduced)", E.run_phase_maps, OUT, verbose=False)
print("[smoke] phase1 rows =", len(ph["aod_cn2"]), flush=True)
print(ph["aod_cn2"].to_string(), flush=True)
print("[smoke] phase2 rows =", len(ph["dt_aod"]), flush=True)
print(ph["dt_aod"].to_string(), flush=True)

# --- 6) 相图精度校核：粗网格+细化 vs 全二分 ---
print("[smoke] ---- 相图精度校核（抽样 vs critical.range_summary 全二分） ----", flush=True)
E.PHASE_AOD = np.geomspace(0.03, 4.0, 25)
E.PHASE_CN2 = np.geomspace(1e-17, 1e-12, 21)
E.PHASE_TARGETS = ("F16",)
E.PHASE_AOD_DT = np.geomspace(0.03, 4.0, 21)
E.PHASE_DT = np.array([-2.0, 0.2, 2.0, 10.0, 30.0])
E.PHASE_ROUNDS = 2
ph2 = sec("run_phase_maps(accuracy subset)", E.run_phase_maps, OUT, verbose=False)
rng = np.random.default_rng(7)
worst = 0.0
for target_key in ("F16",):
    for aod in (0.03, 0.1, 0.587, 2.0, 4.0):
        for cn2 in (1e-17, 1e-15, 1e-13, 1e-12):
            scn = base.with_(target_key=target_key, aod550=float(aod), cn2=float(cn2))
            ref = critical.range_summary(scn, specs=(("R50", "recognize", 0.5),))["R50"]["r_km"]
            row = ph2["aod_cn2"][(np.isclose(ph2["aod_cn2"]["aod550"], aod))
                                 & np.isclose(ph2["aod_cn2"]["cn2"], cn2)]
            v = float(row["R50"].iloc[0]) if len(row) else float("nan")
            if np.isfinite(ref) and np.isfinite(v):
                d = abs(v - ref) / ref
                worst = max(worst, d)
                print(f"  AOD={aod:.3g} Cn2={cn2:.1g}: phase={v:.4f} bisect={ref:.4f} rel={d:.2%}", flush=True)
            else:
                print(f"  AOD={aod:.3g} Cn2={cn2:.1g}: phase={v} bisect={ref} (censored)", flush=True)
print(f"[smoke] 相图 AOD×Cn2 最大相对差 = {worst:.3%}", flush=True)
worst2 = 0.0
for aod in (0.03, 0.1, 0.587, 2.0, 4.0):
    for dt in (-2.0, 0.2, 2.0, 10.0, 30.0):
        scn = base.with_(target_key="F16", aod550=float(aod),
                         target_temp_c=float(base.bg_temp_c + dt))
        ref = critical.range_summary(scn, specs=(("R50", "recognize", 0.5),))["R50"]["r_km"]
        row = ph2["dt_aod"][(np.isclose(ph2["dt_aod"]["aod550"], aod))
                            & np.isclose(ph2["dt_aod"]["dT_K"], dt)]
        v = float(row["R50"].iloc[0]) if len(row) else float("nan")
        if np.isfinite(ref) and np.isfinite(v):
            d = abs(v - ref) / ref
            worst2 = max(worst2, d)
            print(f"  AOD={aod:.3g} dT={dt:g}: phase={v:.4f} bisect={ref:.4f} rel={d:.2%}", flush=True)
        else:
            print(f"  AOD={aod:.3g} dT={dt:g}: phase={v} bisect={ref} (censored)", flush=True)
print(f"[smoke] 相图 ΔT×AOD 最大相对差 = {worst2:.3%}", flush=True)
print("[smoke] OK", flush=True)

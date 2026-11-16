# -*- coding: utf-8 -*-
"""critical.py 修复后的独立校核（brentq 交叉校验 + 单调性 + 地平线 + 快速通道）。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import numpy as np
from scipy.optimize import brentq

from irrecog import chain, critical

base = chain.baseline_scenario()
print("== 1) delta_t_for_p 两侧与 brentq 交叉校验 ==", flush=True)


def dt_ref(scn, r, dT_a, dT_b, task="recognize", p=0.5):
    bs = critical.BandState(scn, r)

    def f(dt):
        d = float(bs.dT_app(scn.bg_temp_c + dt))
        return float(critical.probabilities(np.array([d]), scn.sensor, bs.lam_eff,
                                            bs.r_slant_km, scn.target.d_eff_m,
                                            scn.cn2, scn.n50_set)[task][0]) - p
    return brentq(f, dT_a, dT_b, xtol=1e-8, rtol=1e-12, maxiter=200)


for r in (10.0, 16.216, 5.0):
    t = time.time()
    res = critical.delta_t_for_p(base, r)
    lo_ref = dt_ref(base, r, res["dT_low"] - 0.3, res["dT_low"] + 0.3) if np.isfinite(res["dT_low"]) else float("nan")
    hi_ref = dt_ref(base, r, res["dT_high"] - 0.3, res["dT_high"] + 0.3) if np.isfinite(res["dT_high"]) else float("nan")
    print(f"  r={r:8.3f} km: solver=({res['dT_low']:+.6f}, {res['dT_high']:+.6f}) "
          f"brentq=({lo_ref:+.6f}, {hi_ref:+.6f})  "
          f"Δ=({abs(res['dT_low']-lo_ref):.2e}, {abs(res['dT_high']-hi_ref):.2e}) "
          f"width={res['blind_width_K']:.4f} K ({time.time()-t:.2f}s)", flush=True)

print("== 2) ΔT=0 处 P 严格为 0 ==", flush=True)
for tk in ("F16", "NIMITZ"):
    scn = base.with_(target_key=tk)
    bs = critical.BandState(scn, 10.0)
    print(f"  {tk}: P(dT=0)={bs.probabilities()['recognize'][0]:.6g}", flush=True)

print("== 3) 解析天花板地平线处理 ==", flush=True)
for band, tk in (("MWIR", "F16"), ("LWIR", "HM"), ("LWIR", "F16")):
    scn = chain.baseline_scenario(band=band).with_(target_key=tk)
    t = time.time()
    ana = critical.analytic_resolution_range(scn)
    print(f"  {band} {tk}: R_slant={ana['r_slant_km']:.4f} km, R_ground={ana['r_ground_km']:.4f} km, "
          f"horizon_below={ana['horizon_below']}, censored={ana['censored']!r} ({time.time()-t:.2f}s)", flush=True)

print("== 4) 单调性与洁净极限 ==", flush=True)
r50s = []
for aod in (0.02, 0.1, 0.35, 0.587, 1.0, 2.5, 4.0):
    r = critical.r50(base.with_(aod550=aod))
    r50s.append(r)
print("  R50 vs AOD:", [f"{v:.3f}" for v in r50s], " 单调不增:", all(a >= b - 1e-6 for a, b in zip(r50s, r50s[1:])), flush=True)
r50c = []
for cn2 in (0.0, 1e-16, 1e-15, 1e-14, 1e-13, 1e-12):
    r = critical.r50(base.with_(cn2=cn2))
    r50c.append(r)
print("  R50 vs Cn2:", [f"{v:.3f}" for v in r50c], " 单调不增:", all(a >= b - 1e-6 for a, b in zip(r50c, r50c[1:])), flush=True)
ana = critical.analytic_resolution_range(base)
clean = base.with_(aod550=0.0, cn2=0.0, pwv_cm=0.0)
rc = critical.r50(clean)
print(f"  洁净工况 R50={rc:.4f} km, R_res={ana['r_ground_km']:.4f} km, eta={rc/ana['r_ground_km']:.4f}", flush=True)
print(f"  基线 R50={critical.r50(base):.4f} km, R_res={ana['r_ground_km']:.4f} km, "
      f"eta={critical.r50(base)/ana['r_ground_km']:.4f}, R_slant_res={ana['r_slant_km']:.4f}", flush=True)

print("== 5) 快速通道 vs chain ==", flush=True)
print(" ", critical.validate_fast_path(6, verbose=True), flush=True)

print("== 6) 单点耗时 ==", flush=True)
t = time.time()
for r in np.geomspace(0.2, 400, 20):
    chain.evaluate(base, float(r))
print(f"  20 个唯一距离评估: {time.time()-t:.2f}s", flush=True)

# -*- coding: utf-8 -*-
"""链路 + 临界状态联调自检。"""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))

import numpy as np
from irrecog import chain, critical, params, target as T, sensor as S


def main():
    print("=== 基线链路（F16，40℃，MWIR）===")
    scn = chain.baseline_scenario()
    t0 = time.time()
    for r in (1.0, 3.0, 5.0, 10.0, 20.0):
        ev = chain.evaluate(scn, r)
        print(f"  R={r:5.1f} km  tau={ev['tau_band']:.3f}  dT_app={ev['dT_app_K']:7.3f} K  "
              f"fmax={ev['f_max']:5.2f}  N={ev['n_cycles']:6.2f}  "
              f"P_det={ev['P_detect']:.3f} P_rec={ev['P_rec']:.3f} P_idf={ev['P_ident']:.3f}")
    print(f"  单点 {(time.time()-t0)/5*1000:.1f} ms（含首次开销）")

    print("\n=== 6 目标临界识别距离（基线工况）===")
    for t in T.build_targets():
        scn = chain.baseline_scenario(target_key=t.key)
        res = critical.range_for_p(scn, "recognize", 0.5)
        ana = critical.analytic_resolution_range(scn, "recognize")
        print(f"  {t.name:<12} D_eff={t.d_eff_m:7.2f} m  R50={res['r_km']:8.3f} km "
              f"({res['censored'] or 'ok'})  解析上限={ana['r_ground_km']:8.3f} km")

    print("\n=== 单点耗时（缓存后）===")
    t0 = time.time()
    n = 200
    for i in range(n):
        chain.evaluate(scn, 1.0 + 0.05 * i)
    print(f"  {n} 次评估 {(time.time()-t0):.2f} s → {(time.time()-t0)/n*1000:.2f} ms/次")

    print("\n=== 判据口径敏感性（F16）===")
    for ns in ("NVESD", "JOHNSON"):
        scn = chain.baseline_scenario(n50_set=ns)
        print(f"  {ns:<8} R50={critical.r50(scn):.3f} km")

    print("\n=== 尺寸口径敏感性（F16）===")
    for sr in ("sqrt_area", "max_dim"):
        scn = chain.baseline_scenario(size_rule=sr)
        print(f"  {sr:<10} D_eff={scn.target.d_eff_m:6.2f} m  R50={critical.r50(scn):.3f} km")


if __name__ == "__main__":
    main()

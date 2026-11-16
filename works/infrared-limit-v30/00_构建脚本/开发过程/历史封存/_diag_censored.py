# -*- coding: utf-8 -*-
"""诊断 R50 缺失（censored）的行，确认是否物理合理。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))
import numpy as np
from irrecog import experiments as E, chain, sensor as S

def main():
    grid = np.geomspace(0.5, 320.0, 20)
    base = chain.baseline_scenario()
    cases = [
        ("平台12000m", [base.with_sensor(platform_h_m=12000.0)]),
        ("SEARCH模式", [base.with_(sensor=S.make_sensor("MWIR", preset="SEARCH"))]),
    ]
    for name, scns in cases:
        print(f"--- {name} ---")
        for tk in E.ALL_TARGETS:
            for scn in scns:
                s = scn.with_(target_key=tk)
                m = E.summarize_scn(s, grid)
                r50 = m["R50_ground_km"]
                print(f"  {tk:8s} D_eff={s.target.d_eff_m:7.2f}  R50={r50 if r50 is None else round(r50,2)}"
                      f"  res={m['R_res_analytic_km']:.2f}  {m['censored']}")
    print("\n--- 平台12000m 时的最小斜距与最大 N ---")
    for tk in E.ALL_TARGETS:
        s = base.with_sensor(platform_h_m=12000.0).with_(target_key=tk)
        ev = chain.evaluate(s, 0.5)
        print(f"  {tk:8s} ground=0.5km -> slant={ev['r_slant_km']:.2f} km, N={ev['n_cycles']:.2f}, "
              f"P_rec={ev['P_rec']:.3f}, fmax={ev['f_max']:.1f}")

if __name__ == "__main__":
    main()

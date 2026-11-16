# -*- coding: utf-8 -*-
"""输出报告撰写所需的基线关键数字（供 Lead 核对）。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))
import numpy as np
from irrecog import chain, critical, experiments as E, target as T, params

def main():
    base = chain.baseline_scenario()
    print("目标 | D_eff | R50 | R_res | eta | tau@R50 | dT_app@R50 | N@R50 | P@20km")
    for tk in E.ALL_TARGETS:
        s = E.summarize_scn(base.with_(target_key=tk))
        print(f"{tk:7s} {s['d_eff_m']:8.2f} {str(round(s['R50_ground_km'],2) if s['R50_ground_km'] else None):>8s} "
              f"{s['R_res_analytic_km']:8.2f} {str(round(s['eta'],3) if s['eta'] else None):>6s} "
              f"{str(round(s['tau_at_R50'],3) if s['tau_at_R50'] else None):>7s} "
              f"{str(round(s['dT_app_at_R50'],2) if s['dT_app_at_R50'] else None):>8s} "
              f"{str(round(s['N_at_R50'],1) if s['N_at_R50'] else None):>7s} "
              f"{str(round(s['P_rec_at_20km'],3) if s['P_rec_at_20km'] is not None else None):>7s}")
    print("\n判据/尺寸口径：")
    for ns in ("NVESD", "JOHNSON"):
        s = E.summarize_scn(base.with_(n50_set=ns).with_(target_key="F16"))
        print(f"  {ns}: F16 R50={s['R50_ground_km']:.2f} km")
    for sr in ("sqrt_area", "max_dim"):
        s = E.summarize_scn(base.with_(size_rule=sr).with_(target_key="F16"))
        print(f"  {sr}: F16 R50={s['R50_ground_km']:.2f} km")
    print("\n传感器档位：")
    for preset in ("RECOG", "SEARCH"):
        from irrecog import sensor as S
        scn = base.with_(sensor=S.make_sensor("MWIR", preset=preset))
        print(f"  {preset}: IFOV={scn.sensor.ifov_urad:.1f} urad, f_nyq={scn.sensor.f_nyq_cyc_mrad:.1f}")
        for tk in ("F16", "NIMITZ"):
            s = E.summarize_scn(scn.with_(target_key=tk))
            print(f"     {tk}: R50={s['R50_ground_km']}")
    print("\n临界状态（基线）：")
    for tk in E.ALL_TARGETS:
        scn = base.with_(target_key=tk)
        r50 = E.summarize_scn(scn)["R50_ground_km"] or 10.0
        ref = 0.9 * r50
        a = critical.aod_for_p(scn, ref, "recognize", 0.5)
        c = critical.cn2_for_p(scn, ref, "recognize", 0.5)
        d = critical.delta_t_for_p(scn, 10.0, "recognize", 0.5)
        print(f"  {tk:7s} ref={ref:6.1f}km AODc={a['value']:.3f} Cn2c={c['value']:.3e} dTc={d['value']:.2f}K")

if __name__ == "__main__":
    main()

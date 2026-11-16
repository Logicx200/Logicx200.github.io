# -*- coding: utf-8 -*-
"""联调自检：大气 / 传感器 / 概率链 / 传播速度。"""
import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))

import numpy as np
import irrecog.atmosphere as A
import irrecog.radiometry as R
import irrecog.sensor as S
import irrecog.probability as P
import irrecog.target as T


def main():
    a = A.Atmo()
    print("=== 大气（暂用 MWIR 旧截面）===")
    t0 = time.time()
    for r in (1.0, 5.0, 10.0, 20.0):
        st = A.spectral_state(a, "MWIR", r, 0.0, 8000.0)
        print(f"  MWIR {r:5.1f} km  tau={st['tau_band']:.4f}  Lp={st['l_path']:.5f}  "
              f"lam_eff={st['lam_eff']:.3f}")
    print(f"  单次调用 {(time.time()-t0)/4*1000:.1f} ms；截面源 {A._xsect_band_grid('MWIR')[3]}")

    print("\n=== 波段 LUT / 视在温度 ===")
    lam = A.band_grid("MWIR")
    ctx = R.get_band_context("MWIR", lam)
    for Tc in (20.0, 40.0, 60.0):
        L = ctx.blackbody_band(Tc + 273.15)
        print(f"  黑体 {Tc:4.0f} ℃ -> L={L:.4f} W/m2sr -> T_app={ctx.t_app(L)-273.15:.3f} ℃")

    print("\n=== 传感器 ===")
    s = S.make_sensor("MWIR")
    print(f"  IFOV={s.ifov_urad:.2f} urad  f_nyq={s.f_nyq_cyc_mrad:.2f} cyc/mrad  "
          f"f_cut={s.f_cut_diffraction(4.25):.2f}  deltaT_floor={s.delta_t_floor_k*1000:.1f} mK")
    r0 = S.fried_r0(4.25, 1e-15, 13000.0)
    print(f"  r0(Cn2=1e-15,13km)={r0:.3f} m")
    for dT in (0.01, 0.05, 0.0625, 0.1, 0.5, 2.0, 20.0):
        fm = s.f_max(dT, 4.25, r0)
        print(f"  dT_app={dT:7.4f} K -> f_max={fm:6.2f} cyc/mrad")

    print("\n=== 目标 ===")
    for row in T.summary_table():
        print(f"  {row['name']:<12} A={row['area_proj_m2']:9.2f} m2  D_eff={row['d_eff_m']:7.2f} m  "
              f"D_max={row['d_max_m']:7.2f} m")

    print("\n=== 概率 ===")
    for n50 in (P.n50_set("NVESD")["recognize"], P.n50_set("JOHNSON")["recognize"]):
        print(f"  N50={n50}: " + "  ".join(
            f"N={n:.0f}->P={float(P.p_task(n, n50)):.3f}" for n in (4, 8, 16, 26, 40)))
    print(f"  N(50%) @ NVESD = {P.n_for_probability(0.5, 16.5):.3f} cycles")


if __name__ == "__main__":
    main()

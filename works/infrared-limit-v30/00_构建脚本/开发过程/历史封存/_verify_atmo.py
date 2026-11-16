# -*- coding: utf-8 -*-
"""数值收敛性校核：光谱步长、分层数、路径辐射量级、与 V2.1 量级对比。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))

import numpy as np
import irrecog.params as P
import irrecog.atmosphere as A
import irrecog.radiometry as R


def state(step, layers, band="MWIR", aod=0.587, alpha=1.30, pwv=1.28):
    P.SPECTRAL_STEP_CM = step
    A._xsect_band_grid.cache_clear()
    atmo = A.Atmo(aod550=aod, alpha=alpha, pwv_cm=pwv)
    out = {}
    for r in (1.0, 10.0, 20.0):
        st = A.spectral_state(atmo, band, r, 0.0, 8000.0, n_layers=layers)
        out[r] = (st["tau_band"], st["l_path"], st["lam_eff"], len(st["lam_um"]))
    return out


def main():
    print("=== 光谱步长收敛（n_layers=40，λ=3.7–4.8 μm）===")
    print(f"{'step_cm':>8} {'Npts':>6} " + "".join(f"{'tau@'+str(int(r)):>9}" for r in (1, 10, 20)) + "   L_path@20")
    ref = None
    for step in (0.05, 0.1, 0.2, 0.5, 1.0):
        d = state(step, 40)
        n = d[1.0][3]
        tau = [d[r][0] for r in (1.0, 10.0, 20.0)]
        if step == 0.05:
            ref = tau
        print(f"{step:8.2f} {n:6d} " + "".join(f"{t:9.4f}" for t in tau)
              + f"   {d[20.0][1]:.4f}")
        if ref:
            print(f"{'  相对0.05':>8} 误差 " + "".join(f"{(t-r_)/r_*100:8.2f}%" for t, r_ in zip(tau, ref)))

    P.SPECTRAL_STEP_CM = 0.2
    A._xsect_band_grid.cache_clear()
    print("\n=== 分层数收敛（step=0.2 cm-1）===")
    atmo = A.Atmo()
    for nl in (5, 10, 20, 40, 80, 160):
        st1 = A.spectral_state(atmo, "MWIR", 1.0, 0.0, 8000.0, n_layers=nl)
        st20 = A.spectral_state(atmo, "MWIR", 20.0, 0.0, 8000.0, n_layers=nl)
        print(f"  n_layers={nl:4d}  tau@1={st1['tau_band']:.4f}  tau@20={st20['tau_band']:.4f}  "
              f"Lp@20={st20['l_path']:.4f}")

    print("\n=== 路径辐射物理界限检查 ===")
    lam = A.band_grid("MWIR")
    ctx = R.get_band_context("MWIR", lam)
    Bmin = ctx.blackbody_band(216.65 + 273.15)
    Bmax = ctx.blackbody_band(288.15 + 273.15)
    for r in (0.5, 1.0, 10.0, 50.0):
        st = A.spectral_state(atmo, "MWIR", r, 0.0, 8000.0)
        ok = (st["l_path"] >= 0) and (st["l_path"] <= Bmax * 1.02)
        print(f"  R={r:5.1f} km  Lp={st['l_path']:.4f}  (允许 0..{Bmax:.3f})  {'OK' if ok else '异常'}")

    print("\n=== 极端工况鲁棒性 ===")
    for kw in (dict(aod550=0.0, pwv_cm=0.0), dict(aod550=20.0, pwv_cm=10.0), dict(alpha=0.0), dict(alpha=3.0)):
        at = A.Atmo(**kw)
        st = A.spectral_state(at, "MWIR", 10.0, 0.0, 8000.0)
        print(f"  {kw} -> tau={st['tau_band']:.4f} Lp={st['l_path']:.4f} nan={np.isnan(st['tau_band'])}")

    print("\n=== 与 V2.1 量级对比（3.7–4.8 μm, 15℃/50%/10km）===")
    print("  V2.1 报告：1–20 km 地面目标波段平均透过率约 0.62→0.45")
    print("  本实现（8 km 平台，斜程）：")
    for r in (1.0, 5.0, 10.0, 20.0):
        st = A.spectral_state(atmo, "MWIR", r, 0.0, 8000.0)
        print(f"    R={r:5.1f} km  tau={st['tau_band']:.4f}  Lp={st['l_path']:.4f}")

    print("\n=== 干燥基准 vs 湿基准（水汽敏感性）===")
    for pwv in (0.3, 1.28, 3.0, 6.0):
        at = A.Atmo(pwv_cm=pwv)
        st = A.spectral_state(at, "MWIR", 20.0, 0.0, 8000.0)
        print(f"  PWV={pwv:5.2f} cm  tau@20km={st['tau_band']:.4f}")


if __name__ == "__main__":
    main()

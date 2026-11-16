# -*- coding: utf-8 -*-
"""大气模块数值诊断：定位 L_path 量级异常。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))
import numpy as np
import irrecog.atmosphere as A
import irrecog.radiometry as R


def main():
    a = A.Atmo()
    lam = A.band_grid("MWIR")
    w = R.band_weights(lam)
    print("lam", lam[0], lam[-1], len(lam), "w sum", w.sum())
    print("B_band(293K) =", R.BandContext("MWIR", lam, w).blackbody_band(293.15))

    # 手动复算单层，检查量级
    T, P, rho_v, beta550, n_air = A._profile(a, 0.0)
    print(f"\n地面层: T={T:.1f}K P={P:.1f}hPa rho_v={rho_v:.5f} kg/m3 beta550={beta550:.4f} /km n_air={n_air:.3e} /cm3")

    lam_g, species, temps, path = A._xsect_band_grid("MWIR")
    print("species:", {k: v.shape for k, v in species.items()}, "temps:", temps, "file:", path)
    for sp, g in species.items():
        xs = A._xs_at_T(g, temps, 280.0)
        print(f"  {sp}: xs min={xs.min():.3e} max={xs.max():.3e} mean={xs.mean():.3e}  (cm2/molecule?)")

    n_layers = 40
    dz_m = 8062.3 / n_layers
    print(f"\n层厚 {dz_m:.1f} m")
    total = np.zeros_like(lam)
    for i, z in enumerate(np.linspace(0.5*dz_m, 8000 - 0.5*dz_m, n_layers)):
        T, P, rho_v, beta550, n_air = A._profile(a, z)
        beta_ext = beta550 * (lam / 0.55) ** (-a.alpha) + 0.008735 * (0.55 / lam) ** 4.08 * (P / 1013.0) * (288.15 / T)
        dt = beta_ext * dz_m / 1000.0
        col_h2o = (rho_v / 0.018015) * 6.02214076e23 * dz_m * 1e-4
        if "H2O" in species:
            dt = dt + A._xs_at_T(species["H2O"], temps, T) * col_h2o
        for sp, mix in {"CO2": a.co2_ppm*1e-6, "O3": a.o3_ppb*1e-9, "N2O": a.n2o_ppb*1e-9,
                        "CH4": a.ch4_ppb*1e-9, "CO": a.co_ppb*1e-9}.items():
            if sp in species:
                dt = dt + A._xs_at_T(species[sp], temps, T) * (mix * n_air * dz_m * 100.0)
        total += dt
        if i in (0, 1, 20, 39):
            print(f"  layer {i:2d} z={z:7.0f}m T={T:6.1f} dtau: min={dt.min():.3e} mean={dt.mean():.3e} max={dt.max():.3e}")
    print(f"\n总光学厚度: mean={total.mean():.4f} max={total.max():.2f}")
    print(f"τ_band = Σw·exp(-total) = {np.sum(w*np.exp(-total)):.4f}")
    print(f"L_path = Σw·B·(1-exp(-total)) = {np.sum(w*R.planck(lam,270.0)*(1-np.exp(-total))):.4f}")
    # 逐层版本
    st = A.spectral_state(a, "MWIR", 1.0, 0.0, 8000.0)
    print(f"\nspectral_state: tau_band={st['tau_band']:.4f} l_path={st['l_path']:.4f}")
    print("l_path_lam: min=%.3e mean=%.3e max=%.3e" % (st["l_path_lam"].min(), st["l_path_lam"].mean(), st["l_path_lam"].max()))
    print("tau_band via l_path check: Σw(1-tau) =", float(np.sum(w*(1-st['tau_lam']))))


if __name__ == "__main__":
    main()

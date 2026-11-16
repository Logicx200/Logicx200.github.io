# -*- coding: utf-8 -*-
"""最终校验计算：收敛性、几何口径、Rayleigh 口径、带强度、基线波段透过率。

输出 00_构建脚本/_download/_final_checks.json，供 06_校验/光谱大气校验.md 与
Validation 图使用。所有数值用**当前** 07_光谱数据/xsect_*.npz 现场计算。
"""
import os
import sys
import json
import numpy as np

PROJ = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
sys.path.insert(0, os.path.join(PROJ, "04_模型代码"))
from irrecog import atmosphere as A
from irrecog import params as PR

SPECTRAL = os.path.join(PROJ, "07_光谱数据")
OUT = os.path.join(PROJ, "00_构建脚本", "_download", "_final_checks.json")
R_G, Z_S, Z_T = 20.0, 8000.0, 0.0
BANDS = ("MWIR", "LWIR")


def tau_band(band, r=20.0, n_layers=None, step=None, atmo=None):
    old = PR.SPECTRAL_STEP_CM
    if step is not None:
        PR.SPECTRAL_STEP_CM = float(step)
    try:
        st = A.spectral_state(atmo or A.Atmo(), band, r, Z_T, Z_S,
                              n_layers=n_layers, with_components=True)
    finally:
        PR.SPECTRAL_STEP_CM = old
    return st


def plane_geometry(r_ground_km, z_target_m, z_sensor_m, n_layers):
    """平面地球近似：直线路径按等高分段（用于与球面弦几何对比）。"""
    rg = float(r_ground_km)
    dz = (float(z_sensor_m) - float(z_target_m)) / 1000.0
    path = float(np.hypot(rg, dz))
    t = (np.arange(n_layers) + 0.5) / n_layers
    z_km = (float(z_target_m) + t * (float(z_sensor_m) - float(z_target_m))) / 1000.0
    return dict(h_km=z_km, ds_km=path / n_layers, r_slant_km=path)


def main():
    res = {}
    atmo = A.Atmo()

    # ---------- 基线 τ_band 与分物种（1/10/20 km 地面距离） ----------
    base = {}
    for band in BANDS:
        rows = {}
        for r in (1.0, 10.0, 20.0):
            st = tau_band(band, r=r, atmo=atmo)
            comps = {k: float(np.dot(A._band_cache(band, PR.SPECTRAL_STEP_CM).w,
                                         np.asarray(st["tau_comp"][k], float)))
                     for k in ("H2O", "CO2", "CH4", "O3", "N2O", "CO", "AER", "MOL")}
            prod = np.ones_like(st["tau_lam"])
            for v in st["tau_comp"].values():
                prod = prod * v
            rows["%.0fkm" % r] = dict(
                tau_band=float(st["tau_band"]), l_path=float(st["l_path"]),
                r_slant_km=float(st["r_slant_km"]), lam_eff_um=float(st["lam_eff"]),
                comps=comps,
                tau_comp_product_maxdev=float(np.max(np.abs(prod - st["tau_lam"]))),
                n_layers=int(st["n_layers"]),
            )
        base[band] = rows
    res["baseline_tau_band"] = base

    # ---------- 0.05 vs 0.10 cm⁻¹ 收敛 ----------
    conv_step = {}
    for band in BANDS:
        t05 = tau_band(band, step=0.05)["tau_band"]
        t10 = tau_band(band, step=0.10)["tau_band"]
        conv_step[band] = dict(tau_band_005=float(t05), tau_band_010=float(t10),
                               reldiff_pct=float(100 * (t10 / t05 - 1)))
    res["spectral_step_convergence"] = conv_step

    # ---------- 40 vs 20/80 层收敛 ----------
    conv_lay = {}
    for band in BANDS:
        t20 = tau_band(band, n_layers=20)["tau_band"]
        t40 = tau_band(band, n_layers=40)["tau_band"]
        t80 = tau_band(band, n_layers=80)["tau_band"]
        conv_lay[band] = dict(
            tau_band_20=float(t20), tau_band_40=float(t40), tau_band_80=float(t80),
            reldiff_20_vs_40_pct=float(100 * (t20 / t40 - 1)),
            reldiff_80_vs_40_pct=float(100 * (t80 / t40 - 1)))
    res["layer_convergence"] = conv_lay

    # ---------- 球面曲率 vs 平面近似 ----------
    geo = {}
    for band in BANDS:
        orig = A._geometry
        try:
            A._geometry = plane_geometry
            t_plane = tau_band(band)["tau_band"]
        finally:
            A._geometry = orig
        t_curv = tau_band(band)["tau_band"]
        g_c = A._geometry(R_G, Z_T, Z_S, 40)
        g_p = plane_geometry(R_G, Z_T, Z_S, 40)
        # 空气柱与斜距（同廓线、同层长切分）
        T_c, p_c = A._profile_tp(atmo, g_c["h_km"])
        T_p, p_p = A._profile_tp(atmo, g_p["h_km"])
        k = A._K_B
        col_c = float(np.sum(p_c * 100.0 / (k * T_c) * 1e-6 * g_c["ds_km"] * 1e5))
        col_p = float(np.sum(p_p * 100.0 / (k * T_p) * 1e-6 * g_p["ds_km"] * 1e5))
        hv_c = np.exp(-np.maximum(g_c["h_km"], 0) / atmo.h_wv_km)
        hv_p = np.exp(-np.maximum(g_p["h_km"], 0) / atmo.h_wv_km)
        h2o_c = float(np.sum(hv_c * g_c["ds_km"]))
        h2o_p = float(np.sum(hv_p * g_p["ds_km"]))
        geo[band] = dict(
            r_slant_curved_km=float(g_c["r_slant_km"]),
            r_slant_plane_km=float(g_p["r_slant_km"]),
            r_slant_reldiff_pct=float(100 * (g_p["r_slant_km"] / g_c["r_slant_km"] - 1)),
            air_column_curved=col_c, air_column_plane=col_p,
            air_column_reldiff_pct=float(100 * (col_p / col_c - 1)),
            h2o_path_integral_curved=h2o_c, h2o_path_integral_plane=h2o_p,
            h2o_path_reldiff_pct=float(100 * (h2o_p / h2o_c - 1)),
            tau_band_curved=float(t_curv), tau_band_plane=float(t_plane),
            tau_band_reldiff_pct=float(100 * (t_plane / t_curv - 1)))
    res["curvature_vs_plane"] = geo

    # ---------- Rayleigh 口径修正 ----------
    ray = {}
    for band in BANDS:
        bc = A._band_cache(band, PR.SPECTRAL_STEP_CM)
        st = tau_band(band)
        lam_eff = float(st["lam_eff"])
        tau_vert = 0.008735 * lam_eff ** -4.08            # 垂直光学厚度（正确口径）
        beta0_correct = tau_vert / 8.0                    # 地面消光 km⁻¹
        beta_old = 0.008735 * (0.55 / lam_eff) ** 4.08    # 旧口径：把 τ_vert 误当每 km 系数
        tau_r = -np.log(np.maximum(np.asarray(st["tau_comp"]["MOL"], float), 1e-300))
        t_corr = float(np.dot(bc.w, np.exp(-tau_r)))
        t_old = float(np.dot(bc.w, np.exp(-tau_r * beta_old / beta0_correct)))
        ray[band] = dict(
            lam_eff_um=lam_eff,
            tau_rayleigh_vertical=float(tau_vert),
            beta_rayleigh_km=float(beta0_correct),
            beta_old_formula_km=float(beta_old),
            old_over_correct=float(beta_old / beta0_correct),
            correct_over_old=float(beta0_correct / beta_old),
            slant_rayleigh_tau_bandavg=float(np.dot(bc.w, tau_r)),
            tau_band_correct=float(t_corr),
            tau_band_old=float(t_old),
            band_avg_effect_pct=float(100 * (t_old / t_corr - 1)))
    res["rayleigh_caliber"] = ray

    # ---------- 光谱带强度自检 ΣσΔν（280 K、1 atm，cm⁻¹/(molec cm⁻²)） ----------
    def band_strength(band, sp, lo, hi):
        with np.load(os.path.join(SPECTRAL, "xsect_%s.npz" % band.lower()),
                     allow_pickle=False) as d:
            nu = np.asarray(d["nu"], float)
            key = "%s_T280_P1.00" % sp
            if key not in d.files:
                return None
            sig = np.asarray(d[key], float)
        m = (nu >= lo) & (nu <= hi)
        return float(np.sum(sig[m]) * PR.SPECTRAL_STEP_CM)

    res["band_strength"] = {
        "N2O_nu3_2100_2300": band_strength("MWIR", "N2O", 2100, 2300),
        "CO_1_0_2000_2300": band_strength("MWIR", "CO", 2000, 2300),
        "O3_nu3_900_1150": band_strength("LWIR", "O3", 900, 1150),
        "O3_4.7um_2000_2300": band_strength("MWIR", "O3", 2000, 2300),
        "CO2_4.3um_2200_2500": band_strength("MWIR", "CO2", 2200, 2500),
        "H2O_6.3um_window": band_strength("LWIR", "H2O", 775, 1360),
    }

    # ---------- 元数据 ----------
    for band in BANDS:
        with np.load(os.path.join(SPECTRAL, "xsect_%s.npz" % band.lower()),
                     allow_pickle=False) as d:
            meta = json.loads(str(d["meta"]))
            res.setdefault("xsect_meta", {})[band] = dict(
                n_keys=int(len([k for k in d.files if "_T" in k])),
                temperatures_K=meta.get("temperatures_K"),
                pressures_atm=meta.get("pressures_atm"),
                species_pressure_nodes=meta.get("species_pressure_nodes"),
                missing=meta.get("missing"), engines=meta.get("engines"),
                hapi_tables=meta.get("hapi_tables"),
                grid=meta.get("grid"), generated_at=meta.get("generated_at"))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()

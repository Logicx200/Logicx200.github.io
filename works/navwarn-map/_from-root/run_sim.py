# -*- coding: utf-8 -*-
"""
run_sim.py —— 复杂大气环境红外目标探测仿真：主运行脚本

执行内容：
  1. A/B/C 确定性工况（24 个）→ 指标 CSV
  2. LHS 300 点（LWIR/MWIR 各 150）→ 指标 CSV
  3. GP 代理模型（逐波段）+ 交叉验证 R²
  4. Morris 筛选 + Sobol 全局敏感性
  5. 等性能边界（临界曲线）：MOR*(α)、Cn²*(MOR)、w*(MOR)
  6. 参数相图：Rdet(MOR,α)、R50(MOR,α)、P_d(MOR,R)
  7. 图件与 summary.json

运行：python run_sim.py
输出：sim_results/data/*.csv、sim_results/figures/*.png、sim_results/summary.json
"""

import json
import os
import time

import numpy as np
import pandas as pd

from irsim import model as m
from irsim import experiments as ex
from irsim import plots

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "sim_results")
FIG = os.path.join(OUT, "figures")
DATA = os.path.join(OUT, "data")
for _d in (OUT, FIG, DATA):
    os.makedirs(_d, exist_ok=True)


def _colmap():
    return {"MOR": "mor", "alpha": "alpha", "w": "w", "Cn2": "cn2", "dT": "dT"}


def main():
    t0 = time.time()
    sensor, target, _ = m.default_config()
    print("=== 仿真配置 ===")
    print(f"口径 D={sensor.D*1000:.0f} mm, 焦距 f={sensor.f*1000:.0f} mm, F#={sensor.fnum:.2f}")
    print(f"像元 {sensor.pitch*1e6:.0f} um, IFOV={sensor.ifov_mrad:.3f} mrad, NETD={sensor.netd*1000:.0f} mK")
    print(f"目标 {target.size} m / ΔT={target.dT} K, N50(识别)={sensor.n50}, N50(探测)={sensor.n50_detect}")

    # ------------------------------------------------------------------ #
    # 1. 确定性工况
    # ------------------------------------------------------------------ #
    print("\n[1/7] 确定性工况 ...")
    df_cases = ex.run_cases(sensor, target)
    df_cases.to_csv(os.path.join(DATA, "cases_metrics.csv"),
                    index=False, encoding="utf-8-sig")
    cols = ["case", "band", "tau_band", "dT_app", "fmax", "n_cycles",
            "pd_at_4km", "R50_km", "R90_km", "Rdet_km"]
    print(df_cases[cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    # ------------------------------------------------------------------ #
    # 2. LHS
    # ------------------------------------------------------------------ #
    print("\n[2/7] LHS 采样与批量计算 ...")
    df_lhs = ex.run_lhs(sensor, target)
    df_lhs.to_csv(os.path.join(DATA, "lhs_metrics.csv"),
                  index=False, encoding="utf-8-sig")
    print(f"LHS 点数={len(df_lhs)}，R50 范围 {df_lhs.R50_km.min():.2f}–{df_lhs.R50_km.max():.2f} km")

    # ------------------------------------------------------------------ #
    # 3/4. GP + Morris + Sobol
    # ------------------------------------------------------------------ #
    print("\n[3/7] GP 代理模型与交叉验证 ...")
    print("[4/7] Morris / Sobol 敏感性 ...")
    sobol_rows, morris_rows, cv = [], [], {}
    colmap = _colmap()
    for band in ["LWIR", "MWIR"]:
        sub = df_lhs[df_lhs.band == band].reset_index(drop=True)
        X = ex.to_unit({name: sub[colmap[name]].values for name in ex.PARAM_NAMES})
        for target_name in ["Rdet", "R50"]:
            y = sub[f"{target_name}_km"].values
            r2, _ = ex.gp_cv_r2(X, y)
            gp = ex.GP().fit(X, y)
            cv[f"{band}_{target_name}"] = r2

            def f(u, gp=gp):
                return float(gp.predict(np.asarray(u, float).reshape(1, -1))[0])

            so = ex.sobol_indices(f, len(ex.PARAM_NAMES), N=1024, seed=11)
            mo = ex.morris(f, len(ex.PARAM_NAMES), r=10, seed=12)
            for k, name in enumerate(ex.PARAM_NAMES):
                sobol_rows.append(dict(band=band, target=target_name, param=name,
                                       S1=float(so["S1"][k]), ST=float(so["ST"][k])))
                morris_rows.append(dict(band=band, target=target_name, param=name,
                                        mu=float(mo["mu"][k]),
                                        mu_star=float(mo["mu_star"][k]),
                                        sigma=float(mo["sigma"][k])))
            print(f"  {band} {target_name}: GP 5-fold CV R2 = {r2:.3f}")

    df_sobol = pd.DataFrame(sobol_rows)
    df_sobol.to_csv(os.path.join(DATA, "sobol_indices.csv"),
                    index=False, encoding="utf-8-sig")
    df_morris = pd.DataFrame(morris_rows)
    df_morris.to_csv(os.path.join(DATA, "morris_indices.csv"),
                     index=False, encoding="utf-8-sig")
    for band in ["LWIR", "MWIR"]:
        d = df_sobol[(df_sobol.band == band) & (df_sobol.target == "Rdet")]
        d = d.sort_values("ST", ascending=False)
        print(f"  {band} Rdet Sobol ST: " +
              ", ".join(f"{r.param}={r.ST:.2f}" for r in d.itertuples()))

    # ------------------------------------------------------------------ #
    # 5. 临界曲线（探测任务，Rdet=8 km）
    # ------------------------------------------------------------------ #
    print("\n[5/7] 等性能边界（探测任务 Rdet=8 km）...")
    df_crit = ex.critical_curves(sensor, target, R_target=8.0, band="LWIR", n50=2.0)
    df_crit.to_csv(os.path.join(DATA, "critical_curves_Rdet8.csv"),
                   index=False, encoding="utf-8-sig")
    ok = df_crit.dropna(subset=["y"])
    print(f"  有效临界点 {len(ok)}/{len(df_crit)}")

    # ------------------------------------------------------------------ #
    # 6. 相图
    # ------------------------------------------------------------------ #
    print("\n[6/7] 参数相图 ...")
    mor_grid = np.geomspace(0.5, 23.0, 36)
    alpha_grid = np.linspace(0.0, 1.6, 21)
    phase_data = []
    for band in ["LWIR", "MWIR"]:
        Z = ex.phase_R50_grid(sensor, target, band, mor_grid, alpha_grid, n50=sensor.n50_detect)
        np.savez(os.path.join(DATA, f"phase_Rdet_{band}.npz"),
                 mor=mor_grid, alpha=alpha_grid, Z=Z)
        for i, mor in enumerate(mor_grid):
            for j, a in enumerate(alpha_grid):
                phase_data.append(dict(band=band, mor=mor, alpha=a, Rdet_km=Z[i, j]))
        try:
            plots.fig_phase_R50(os.path.join(FIG, f"fig02_Rdet_phase_{band}.png"),
                                sensor, target, mor_grid, alpha_grid, Z, band,
                                levels=(8.0,), task_label="探测距离 Rdet")
        except Exception as e:  # 画图失败不阻断
            print("  [warn] 相图绘制失败:", e)
    pd.DataFrame(phase_data).to_csv(os.path.join(DATA, "phase_Rdet_grid.csv"),
                                    index=False, encoding="utf-8-sig")

    # 识别相图（次要）
    Z_id = ex.phase_R50_grid(sensor, target, "LWIR", mor_grid, alpha_grid, n50=sensor.n50)
    np.savez(os.path.join(DATA, "phase_R50_LWIR.npz"), mor=mor_grid, alpha=alpha_grid, Z=Z_id)
    try:
        plots.fig_phase_R50(os.path.join(FIG, "fig02b_R50_phase_LWIR.png"),
                            sensor, target, mor_grid, alpha_grid, Z_id, "LWIR",
                            levels=(2.0,), task_label="识别距离 R50")
    except Exception as e:
        print("  [warn] 识别相图绘制失败:", e)

    # P_d(MOR, R) 相图
    R_grid = np.linspace(0.5, 12.0, 48)
    Zp = ex.phase_pd_grid(sensor, target, "LWIR", mor_grid, R_grid, n50=sensor.n50_detect)
    np.savez(os.path.join(DATA, "phase_pd_LWIR.npz"), mor=mor_grid, R=R_grid, Z=Zp)
    try:
        plots.fig_pd_heatmap(os.path.join(FIG, "fig07_Pd_phase_LWIR.png"),
                             sensor, target, mor_grid, R_grid, Zp, "LWIR")
    except Exception as e:
        print("  [warn] P_d 相图绘制失败:", e)

    # ------------------------------------------------------------------ #
    # 6b. 天气因子两两组合热力图
    # ------------------------------------------------------------------ #
    print("\n[6b/7] 天气因子两两组合热力图 ...")
    units = {"MOR": "km", "alpha": "", "w": "cm", "Cn2": "m^-2/3"}
    matrix_rows = []

    def make_panels(band, metric):
        panels = []
        for pair in ex.WEATHER_PAIRS:
            X, Y, Z = ex.weather_pair_grid(pair, band, sensor, target, metric=metric)
            panels.append(dict(
                xname=pair[0], yname=pair[1],
                xunit=units[pair[0]], yunit=units[pair[1]],
                X=X, Y=Y, Z=Z,
                xlog=pair[0] in ("MOR", "Cn2"),
                ylog=pair[1] in ("MOR", "Cn2"),
            ))
            for i, xx in enumerate(X):
                for j, yy in enumerate(Y):
                    matrix_rows.append(dict(
                        band=band, metric=metric,
                        xname=pair[0], yname=pair[1],
                        x=float(xx), y=float(yy), value=float(Z[i, j]),
                    ))
        return panels

    fixed_text = "未在坐标轴上的参数取标称值 MOR=5, α=1.3, w=1.5, Cn²=1e-14, ΔT=10 K"
    for band in ["LWIR", "MWIR"]:
        panels = make_panels(band, "Rdet")
        idx = 8 if band == "LWIR" else 9
        plots.fig_weather_matrix(os.path.join(FIG, f"fig{idx:02d}_weather_matrix_{band}_Rdet.png"),
                                 panels, band, "探测距离 Rdet (km)", levels=[4, 6, 8],
                                 vmax=10, fixed_text=fixed_text)
    panels = make_panels("LWIR", "R50")
    plots.fig_weather_matrix(os.path.join(FIG, "fig10_weather_matrix_LWIR_R50.png"),
                             panels, "LWIR", "识别距离 R50 (km)",
                             levels=[1, 1.5, 2, 2.5], vmax=3, fixed_text=fixed_text)
    pd.DataFrame(matrix_rows).to_csv(os.path.join(DATA, "weather_matrix.csv"),
                                     index=False, encoding="utf-8-sig")

    Xc, Yc, Zl = ex.weather_pair_grid(("MOR", "alpha"), "LWIR", sensor, target, metric="Rdet")
    _, _, Zm = ex.weather_pair_grid(("MOR", "alpha"), "MWIR", sensor, target, metric="Rdet")
    plots.fig_band_compare(os.path.join(FIG, "fig11_band_compare_Rdet.png"),
                           Xc, Yc, Zl, Zm, levels=[4, 6, 8],
                           metric_label="探测距离 Rdet (km)", fixed_text=fixed_text)

    # ------------------------------------------------------------------ #
    # 7. 其余图件
    # ------------------------------------------------------------------ #
    print("\n[7/7] 其余图件 ...")
    plots.fig_spectra(os.path.join(FIG, "fig01_spectra.png"), sensor, target)
    plots.fig_critical(os.path.join(FIG, "fig03_critical_curves.png"), df_crit, 8.0)
    plots.fig_pd_curves(os.path.join(FIG, "fig04_pd_curves.png"), sensor, target)
    plots.fig_sobol(os.path.join(FIG, "fig05_sobol.png"),
                    {k: np.array([r[k] for r in sobol_rows
                                  if r["band"] == "LWIR" and r["target"] == "Rdet"])
                     for k in ("S1", "ST")},
                    {k: np.array([r[k] for r in sobol_rows
                                  if r["band"] == "MWIR" and r["target"] == "Rdet"])
                     for k in ("S1", "ST")})
    plots.fig_turbulence(os.path.join(FIG, "fig06_turbulence.png"), sensor, target)

    # ------------------------------------------------------------------ #
    # summary
    # ------------------------------------------------------------------ #
    def get_case(cid):
        r = df_cases[df_cases.case == cid].iloc[0]
        return dict(band=r.band, tau_band=float(r.tau_band), dT_app=float(r.dT_app),
                    fmax=float(r.fmax), n_cycles=float(r.n_cycles),
                    pd_at_4km=float(r.pd_at_4km), R50_km=float(r.R50_km),
                    R90_km=float(r.R90_km), Rdet_km=float(r.Rdet_km))

    crit = {}
    for kind in ["MOR_vs_alpha", "Cn2_vs_MOR", "w_vs_MOR"]:
        d = df_crit[(df_crit.kind == kind)].dropna(subset=["y"])
        crit[kind] = [dict(x=float(x), y=float(y)) for x, y in zip(d.x, d.y)]

    summary = dict(
        model="irsim v1.0 简化物理模型（非逐线/带模型；正式版以 libRadtran/COSSIM 替换）",
        sensor=dict(D_m=sensor.D, f_m=sensor.f, fnum=sensor.fnum,
                    ifov_mrad=sensor.ifov_mrad, netd_K=sensor.netd,
                    n50_ident=sensor.n50, n50_detect=sensor.n50_detect),
        target=dict(size_m=target.size, dT_K=target.dT),
        cases={c: get_case(c) for c in ["A0", "B3", "B16", "B17", "C1", "C3", "C5"]},
        gp_cv_r2=cv,
        sobol={b: df_sobol[df_sobol.band == b].to_dict(orient="records")
               for b in ["LWIR", "MWIR"]},
        critical=crit,
        runtime_s=round(time.time() - t0, 1),
    )
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=2)

    print("\n=== 完成 ===")
    print(f"耗时 {summary['runtime_s']} s")
    print(f"输出目录: {OUT}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""最终数据关键数字汇总（发 Lead 用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))
DATA = os.path.join(ROOT, "03_数据")

import numpy as np
import pandas as pd

TORDER = ["HM", "F16", "F22", "AGZFSC", "ALBK", "NIMITZ"]
TSHORT = {"F16": "F16", "F22": "F22", "NIMITZ": "尼米兹", "ALBK": "阿利伯克",
          "HM": "悍马", "AGZFSC": "爱国者"}


def load(*parts, **kw):
    return pd.read_csv(os.path.join(DATA, *parts), encoding="utf-8-sig", **kw)


s00 = load("单变量对比", "S00_全扫描指标汇总.csv")
s00["_x"] = pd.to_numeric(s00["sweep_value"], errors="coerce")
s01 = s00[s00.sweep_id == "S01"]
s02 = s00[s00.sweep_id == "S02"]
s04 = s00[s00.sweep_id == "S04"]
s07 = s00[s00.sweep_id == "S07"]

print("== 基线 R50（S01，MWIR，ΔT=20K，AOD=0.587，PWV=1.28，Cn²=1e-15）==")
for _, r in s01.set_index("target").loc[TORDER].reset_index().iterrows():
    print(f"  {TSHORT[r['target']]:5s}: R50={r['R50_ground_km']:8.3f} km  R90={r['R90_ground_km']:>8}"
          f"  Rdet50={r['Rdet50_ground_km']:.2f}  Rident50={r['Rident50_ground_km']:.2f}"
          f"  Rres={r['R_res_analytic_km']:.2f}  eta={r['eta']:.3f}  Pmax={r['P_rec_max']:.3f}"
          f"  τ@R50={r['tau_at_R50']:.3f}")

print("\n== 波段对比（S02 汇总 + 波段对比表基线行）==")
band = load("波段对比", "波段对比_R50.csv")
for tk in TORDER:
    m = s02[(s02.target == tk) & (s02.band == "MWIR")]
    l = s02[(s02.target == tk) & (s02.band == "LWIR")]
    mv = float(m["R50_ground_km"].iloc[0]) if len(m) else np.nan
    lv = float(l["R50_ground_km"].iloc[0]) if len(l) else np.nan
    ratio = lv / mv if np.isfinite(mv) and np.isfinite(lv) else np.nan
    print(f"  {TSHORT[tk]:5s}: MWIR R50={mv:8.3f} km, LWIR R50={lv:8.3f} km, LWIR/MWIR={ratio:.3f}")

print("\n== AOD 影响（S04，R50 km，AOD=0.02→4.0）==")
for tk in TORDER:
    g = s04[s04.target == tk].dropna(subset=["_x"]).set_index("_x")["R50_ground_km"]
    vals = [float(g.loc[a]) for a in (0.02, 0.35, 0.6, 1.6, 4.0) if a in g.index and pd.notna(g.loc[a])]
    if len(vals) == 5:
        print(f"  {TSHORT[tk]:5s}: {vals[0]:8.3f} → {vals[1]:8.3f} → {vals[2]:8.3f} → {vals[3]:8.3f} → {vals[4]:8.3f}"
              f"   (0.02→4.0 降幅 {100*(1-vals[4]/vals[0]):.1f}%)")

print("\n== Cn² 影响（S07，R50 km，Cn²=0→1e-13）==")
cn_vals = [0.0, 1e-17, 1e-15, 3e-15, 1e-14, 3e-14, 1e-13, 1e-12]
for tk in TORDER:
    g = s07[s07.target == tk].dropna(subset=["_x"]).set_index("_x")["R50_ground_km"]
    parts = []
    for c in cn_vals:
        if c in g.index:
            v = g.loc[c]
            parts.append("nan" if pd.isna(v) else f"{float(v):.2f}")
        else:
            parts.append("-")
    print(f"  {TSHORT[tk]:5s}: 0→1e-17→1e-15→3e-15→1e-14→3e-14→1e-13→1e-12: " + " / ".join(parts))

print("\n== 临界状态（r_ref=0.5R50 主列 + 10 km 附列）==")
crit = load("临界状态", "临界状态汇总.csv")
cols = ["target", "R50_ground_km", "r_ref_km", "eta", "AOD_crit", "Cn2_crit",
        "dT_blind_low_K", "dT_blind_high_K", "dT_blind_width_K",
        "dT_blind_width_10km", "D_crit", "NETD_crit", "R_contrast_floor_km"]
print(crit[[c for c in cols if c in crit.columns]].to_string(index=False))
print("\n  截断原因（非空 censored 字段）：")
for _, r in crit.iterrows():
    notes = []
    for c in crit.columns:
        if "censor" in c.lower() and pd.notna(r[c]) and str(r[c]).strip() not in ("", "nan"):
            notes.append(f"{c}={str(r[c]).strip()}")
    print(f"   {TSHORT[r['target']]:5s}: " + ("; ".join(notes) if notes else "无"))

print("\n== 环境工况 ==")
env = load("真实气候工况", "环境工况_识别临界距离.csv")
for q in ("p10", "median", "p90"):
    sub = pd.to_numeric(env[env.quantile == q]["R50_ground_km"], errors="coerce")
    print(f"  {q:7s}: {sub.min():.2f} – {sub.max():.2f} km, 中位 {sub.median():.2f}")
print("\n  按目标中位（median 行）：")
med = env[env.quantile == "median"].groupby("target")["R50_ground_km"].median()
for tk in TORDER:
    print(f"    {TSHORT[tk]:5s}: {med.get(tk):8.2f} km")

print("\n== 相图范围 ==")
p1 = load("相图", "相图_AODxCn2.csv")
p2 = load("相图", "相图_dT_AOD.csv")
r1 = pd.to_numeric(p1["R50"], errors="coerce")
r2 = pd.to_numeric(p2["R50"], errors="coerce")
print(f"  AOD×Cn²: {len(p1)} 格, 有效 {r1.notna().sum()}, R50 {r1.min():.2f}–{r1.max():.2f} km")
for tk in ("F16", "NIMITZ"):
    sub = pd.to_numeric(p1[p1.target == tk]["R50"], errors="coerce")
    print(f"    {TSHORT[tk]:5s}: {sub.notna().sum()}/{len(sub)} 有效, {sub.min():.2f}–{sub.max():.2f} km")
print(f"  ΔT×AOD: {len(p2)} 格, 有效 {r2.notna().sum()}, R50 {r2.min():.2f}–{r2.max():.2f} km")
print()
print("== 文件清单 ==")
for root, dirs, files in os.walk(DATA):
    for fn in sorted(files):
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, DATA)
        if fn.endswith((".csv", ".xlsx")):
            print(f"  {rel:55s} {os.path.getsize(p)/1024:9.1f} KB")

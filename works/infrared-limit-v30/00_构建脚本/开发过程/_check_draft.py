# -*- coding: utf-8 -*-
"""草稿版数据完备性 + 关键数字核对（供 Lead 汇报用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))
DATA = os.path.join(ROOT, "03_数据")

import numpy as np
import pandas as pd


def load(*parts, **kw):
    p = os.path.join(DATA, *parts)
    if not os.path.exists(p):
        print(f"  [缺失] {p}")
        return None
    return pd.read_csv(p, encoding="utf-8-sig", **kw)


print("=" * 78)
print("1) 文件与规模核对")
print("=" * 78)
lt = load("全工况长表", "eval_long.csv.gz",
          usecols=["sweep_id", "sweep_value", "target", "r_ground_km"])
print(f"  长表 eval_long.csv.gz: {len(lt)} 行, 列 {len(pd.read_csv(os.path.join(DATA,'全工况长表','eval_long.csv.gz'), encoding='utf-8-sig', nrows=1).columns)}")
print("  各组行数:\n" + lt.groupby("sweep_id").size().to_string())
s00 = load("单变量对比", "S00_全扫描指标汇总.csv")
print(f"  S00 汇总: {len(s00)} 行, 列数 {len(s00.columns) if s00 is not None else '-'}")
if s00 is not None:
    print("  每组行数:\n" + s00.groupby("sweep_id").size().to_string())
    miss = []
    for sid, g in s00.groupby("sweep_id"):
        per = g.groupby("sweep_value")["target"].nunique()
        if (per < 6).any():
            miss.append((sid, per[per < 6].to_dict()))
    print("  每组×6 目标不齐:", miss if miss else "无")
env = load("真实气候工况", "环境工况_识别临界距离.csv")
print(f"  环境工况: {len(env) if env is not None else '-'} 行, "
      f"环境数 {env['env_key'].nunique() if env is not None else '-'}, "
      f"目标数 {env['target'].nunique() if env is not None else '-'}")
crit = load("临界状态", "临界状态汇总.csv")
print(f"  临界状态: {len(crit) if crit is not None else '-'} 行, 列数 {len(crit.columns) if crit is not None else '-'}")
band = load("波段对比", "波段对比_R50.csv")
print(f"  波段对比: {len(band) if band is not None else '-'} 行, "
      f"band={sorted(band['band'].unique()) if band is not None else '-'}")
p1 = load("相图", "相图_AODxCn2.csv")
print(f"  相图 AOD×Cn²: {len(p1) if p1 is not None else '-'} 行, "
      f"AOD {p1['aod550'].nunique() if p1 is not None else '-'} × "
      f"Cn² {p1['cn2'].nunique() if p1 is not None else '-'} × "
      f"目标 {p1['target'].nunique() if p1 is not None else '-'}")
p2 = load("相图", "相图_dT_AOD.csv")
print(f"  相图 ΔT×AOD: {len(p2) if p2 is not None else '-'} 行, "
      f"ΔT {p2['dT_K'].nunique() if p2 is not None else '-'} × "
      f"AOD {p2['aod550'].nunique() if p2 is not None else '-'}")
xlsx = os.path.join(DATA, "识别极限_数据汇总.xlsx")
print(f"  XLSX: {'存在' if os.path.exists(xlsx) else '缺失（run_all.py --xlsx 生成）'}")

print()
print("=" * 78)
print("2) 基线关键数字（S01 & S02）")
print("=" * 78)
TORDER = ["HM", "F16", "F22", "AGZFSC", "ALBK", "NIMITZ"]
if s00 is not None:
    s1 = s00[s00["sweep_id"] == "S01"]
    print("  S01 6 目标（MWIR 基线，ΔT=20K）：")
    for _, r in s1.iterrows():
        print(f"    {r['target']:7s} R50={r['R50_ground_km']:8.3f} km  R90={r['R90_ground_km']:>8}"
              f"  Rdet50={r['Rdet50_ground_km']}  Rres={r['R_res_analytic_km']:.2f}"
              f"  eta={r['eta']:.3f}  Pmax={r['P_rec_max']:.3f}")
    s2 = s00[s00["sweep_id"] == "S02"]
    print("  S02 MWIR vs LWIR：")
    for tk in TORDER:
        m = s2[(s2["target"] == tk) & (s2["band"] == "MWIR")]
        l = s2[(s2["target"] == tk) & (s2["band"] == "LWIR")]
        if len(m) and len(l):
            mv, lv = float(m["R50_ground_km"].iloc[0]), float(l["R50_ground_km"].iloc[0])
            print(f"    {tk:7s} MWIR={mv:8.3f} km  LWIR={lv:8.3f} km  比值 LWIR/MWIR={lv/mv:.3f}")
    s4 = s00[s00["sweep_id"] == "S04"]
    print("  S04 AOD 影响（R50 km，AOD=0.02 → 0.6 → 4.0）：")
    for tk in TORDER:
        g = s4[s4["target"] == tk].set_index("sweep_value")["R50_ground_km"]
        vals = []
        for a in (0.02, 0.6, 4.0):
            if a in g.index:
                vals.append(float(g.loc[a]))
        if len(vals) == 3:
            print(f"    {tk:7s} {vals[0]:8.3f} → {vals[1]:8.3f} → {vals[2]:8.3f}  (降幅 {100*(1-vals[2]/vals[0]):.1f}%)")
    s7 = s00[s00["sweep_id"] == "S07"]
    print("  S07 湍流影响（R50 km，Cn²=1e-17 → 1e-15 → 1e-13）：")
    for tk in TORDER:
        g = s7[s7["target"] == tk].set_index("sweep_value")["R50_ground_km"]
        vals = [float(g.loc[1e-17]) if 1e-17 in g.index else np.nan,
                float(g.loc[1e-15]) if 1e-15 in g.index else np.nan,
                float(g.loc[1e-13]) if 1e-13 in g.index else np.nan]
        print(f"    {tk:7s} {vals[0]:8.3f} → {vals[1]:8.3f} → {vals[2] if np.isfinite(vals[2]) else 'NaN':>8}")

print()
print("=" * 78)
print("3) 单调性抽查（R50 随 AOD / Cn² 不增）")
print("=" * 78)
for sid, xcol in (("S04", "aod550"), ("S07", "cn2")):
    d = load("单变量对比", next((f for f in os.listdir(os.path.join(DATA, "单变量对比"))
                                if f.startswith(sid + "_")), ""))
    if d is None:
        continue
    bad = []
    for tk, g in d.groupby("target"):
        g = g.sort_values(xcol)
        y = pd.to_numeric(g["R50_ground_km"], errors="coerce").to_numpy()
        y = y[np.isfinite(y)]
        if np.any(np.diff(y) > 1e-6):
            bad.append(tk)
    print(f"  {sid} 非单调目标: {bad if bad else '无'}")

print()
print("=" * 78)
print("4) 临界状态表（r_ref = 0.5·R50）")
print("=" * 78)
if crit is not None:
    cols = ["target", "R50_ground_km", "r_ref_km", "AOD_crit", "Cn2_crit",
            "dT_blind_low_K", "dT_blind_high_K", "dT_blind_width_K",
            "dT_blind_width_10km", "D_crit", "NETD_crit", "R_contrast_floor_km"]
    cols = [c for c in cols if c in crit.columns]
    print(crit[cols].to_string(index=False))

print()
print("=" * 78)
print("5) 环境工况范围 / 波段对比基线")
print("=" * 78)
if env is not None:
    med = pd.to_numeric(env["R50_ground_km"], errors="coerce")
    print(f"  R50 范围 {med.min():.3f}–{med.max():.3f} km，中位 {med.median():.3f} km")
    for q in ("p10", "median", "p90"):
        sub = med[env["quantile"] == q]
        print(f"    {q:7s}: {sub.min():.2f} – {sub.max():.2f} km")
if band is not None and "sweep_var" in band.columns:
    base = band[(np.isclose(band["aod550"], 0.587)) & (np.isclose(band["pwv_cm"], 1.28))]
    print("  波段对比基线（AOD=0.587, PWV=1.28）：")
    for _, r in base.sort_values(["target", "band"]).iterrows():
        print(f"    {r['target']:7s} {r['band']}: R50={r['R50_ground_km']:.3f} km, "
              f"R90={r['R90']}, eta={r['eta']:.3f}, censored={r['censored']!r}")
print()
print("完成核对")

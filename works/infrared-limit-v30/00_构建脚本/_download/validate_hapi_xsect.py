# -*- coding: utf-8 -*-
"""独立实现校验：本实现（HITRAN2020 逐线，三温度四气压节点）vs HAPI absorptionCoefficient_Voigt。

做法：把参考项目 db_raw 中的 HITRAN2020 原始线表（.par 块）装配成 HAPI 表，
在 280 K、1 atm 下用 HAPI 独立计算 H2O / CO2 / CH4 的逐线截面，与本项目
07_光谱数据/xsect_*.npz 的 T280/P1.00 节点逐点比较：

* 强吸收点（σ_HAPI > max(1e-23, 1%·窗口最大)）的相对差中位数/p90/最大值；
* dB/dT 加权的窗口平均截面相对差（等价于“波段平均”口径）；
* 用参考项目斜程等效柱量做单层波段平均透过率对比（合成口径，仅作一致性量级）。

输出：_hapi_validation.json + _hapi_validation.npz（供 Validation 图使用）
"""
import os
import sys
import io
import json
import time
import contextlib
import numpy as np
import multiprocessing as mp

PROJ = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
REF = r"F:\DeepSeek工作区\hitran_slant"
BOOT = os.path.join(PROJ, "00_构建脚本")
sys.path.insert(0, BOOT)
import build_xsect as BX
import hapi

RAW = os.path.join(REF, "db_raw")
TMP = os.path.join(BOOT, "_download", "_hapi_selftest_hapi")
os.makedirs(TMP, exist_ok=True)
SPEC = {"H2O": 1, "CO2": 2, "CH4": 6}
T_NODE, P_NODE = 280.0, 1.0
T_REF_K = 293.15

WINDOWS = [
    # (物种, 波段, ν_lo, ν_hi)
    ("H2O", "MWIR", 1e4 / 4.8, 1e4 / 3.7),
    ("CO2", "MWIR", 1e4 / 4.8, 1e4 / 3.7),
    ("CH4", "MWIR", 1e4 / 4.8, 1e4 / 3.7),
    ("H2O", "LWIR", 1e4 / 12.0, 1e4 / 8.0),
    ("CO2", "LWIR", 1e4 / 12.0, 1e4 / 8.0),
    ("CH4", "LWIR", 1150.0, 1360.0),        # CH4 7.7 μm 带只落在 LWIR 上边缘
]
# 参考项目斜程路径的等效柱量（molecules/cm²），用于“单层合成波段平均透过率”
COLUMN = {"H2O": 1.34e23, "CO2": 2.36e22, "CH4": 1.08e20}


def band_weights(lam):
    lam_m = np.asarray(lam, float) * 1e-6
    x = 6.62607015e-34 * 2.99792458e8 / (lam_m * 1.380649e-23 * T_REF_K)
    B = 2 * 6.62607015e-34 * 2.99792458e8 ** 2 / lam_m ** 5 / np.expm1(x) * 1e-6
    w = B * x * np.exp(x) / np.expm1(x) / T_REF_K * np.abs(np.gradient(np.asarray(lam, float)))
    return w / w.sum()


def make_hapi_table(sp, out_dir):
    """从 db_raw 的 250 cm⁻¹ 块装配某分子的完整 HAPI 表。"""
    mol = SPEC[sp]
    rows = []
    for a in range(475, 5025, 250):
        fn = os.path.join(RAW, "%s_%05d_%05d.par" % (sp, a, a + 250))
        if not os.path.exists(fn):
            continue
        with open(fn, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if len(line) >= 67 and int(line[0:2]) == mol:
                    rows.append(line.rstrip("\n").ljust(160))
    rows.sort(key=lambda s: float(s[3:15]))
    name = sp + "_val"
    dfn = os.path.join(out_dir, name + ".data")
    with open(dfn, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rows) + "\n")
    hdr = dict(BX._HEADER_TEMPLATE)
    hdr.update(table_name=name, number_of_rows=len(rows),
               size_in_bytes=os.path.getsize(dfn), comment="HAPI validation table")
    with open(os.path.join(out_dir, name + ".header"), "w", encoding="utf-8") as f:
        json.dump(hdr, f, indent=2)
    print("[hapi-table] %s: %d 行" % (sp, len(rows)), flush=True)
    return name


def work(task):
    sp, band, vlo, vhi = task
    mol = SPEC[sp]
    iso = [i for (m, i) in sorted(hapi.ISO) if m == mol]
    # 关键：让 HAPI 在**本项目截面网格的同一批谱点**上计算，避免 0.05 cm⁻¹ 网格
    # 相位错位在陡峭线翼上造成伪差异（网格起点不同 → 线心与采样点相对位置不同）。
    path = os.path.join(PROJ, "07_光谱数据", "xsect_%s.npz" % band.lower())
    with np.load(path, allow_pickle=False) as d:
        nu_src = np.asarray(d["nu"], float)
    sel = (nu_src >= vlo - 1e-6) & (nu_src <= vhi + 1e-6)
    nu = nu_src[sel]
    with contextlib.redirect_stdout(io.StringIO()):
        hapi.db_begin(TMP)
        nu_h, coef_h = hapi.absorptionCoefficient_Voigt(
            Components=[(mol, i) for i in iso], SourceTables=[sp + "_val"],
            WavenumberGrid=nu, Environment={"p": P_NODE, "T": T_NODE},
            HITRAN_units=True, Diluent={"air": 1.0})
    nu_h = np.asarray(nu_h, float)
    coef_h = np.asarray(coef_h, float)
    if nu_h.size != nu.size:
        coef_h = np.interp(nu, nu_h, coef_h)
    with np.load(path, allow_pickle=False) as d:
        key = "%s_T%d_P%.2f" % (sp, int(T_NODE), P_NODE)
        coef_o = np.asarray(d[key], float)[sel]

    lam = 1e4 / nu
    w = band_weights(lam)
    strong = coef_h > max(1e-23, 0.01 * float(coef_h.max()))
    rel = (coef_o[strong] - coef_h[strong]) / np.maximum(coef_h[strong], 1e-300)
    wavg_h = float(np.sum(w * coef_h))
    wavg_o = float(np.sum(w * coef_o))
    # 合成单层波段平均透过率（同一柱量、同一加权）
    t_h = float(np.sum(w * np.exp(-coef_h * COLUMN[sp])))
    t_o = float(np.sum(w * np.exp(-coef_o * COLUMN[sp])))
    out = dict(species=sp, band=band, nu_lo=float(nu[0]), nu_hi=float(nu[-1]),
               n_points=int(nu.size), n_strong=int(strong.sum()),
               median_rel_pct=float(100 * np.median(rel)),
               p90_abs_rel_pct=float(100 * np.percentile(np.abs(rel), 90)),
               max_abs_rel_pct=float(100 * np.percentile(np.abs(rel), 99.9)),
               bandavg_sigma_hapi=wavg_h, bandavg_sigma_ours=wavg_o,
               bandavg_sigma_reldiff_pct=float(100 * (wavg_o / wavg_h - 1)),
               synth_T_hapi=t_h, synth_T_ours=t_o,
               synth_T_reldiff_pct=float(100 * (t_o / t_h - 1)))
    return out, nu, coef_h, coef_o


def main():
    t0 = time.time()
    for sp in SPEC:
        make_hapi_table(sp, TMP)
    print("[plan] %d 个窗口（%d 过程）" % (len(WINDOWS), 2), flush=True)
    rows, keep = [], {}
    with mp.Pool(2) as pool:
        for i, (out, nu, ch, co) in enumerate(pool.imap_unordered(work, WINDOWS), 1):
            rows.append(out)
            keep[(out["species"], out["band"])] = (nu, ch, co)
            print("[progress %d/%d] %s %s: 强吸收点中位差 %+.2f%% | 窗口加权平均差 %+.3f%%"
                  " | 合成 T 差 %+.2f%% (%.0fs)"
                  % (i, len(WINDOWS), out["species"], out["band"],
                     out["median_rel_pct"], out["bandavg_sigma_reldiff_pct"],
                     out["synth_T_reldiff_pct"], time.time() - t0), flush=True)
    base = os.path.join(BOOT, "_download")
    with open(os.path.join(base, "_hapi_validation.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    npz = {}
    for (sp, band), (nu, ch, co) in keep.items():
        npz["%s_%s_nu" % (sp, band)] = nu
        npz["%s_%s_hapi" % (sp, band)] = ch
        npz["%s_%s_ours" % (sp, band)] = co
    np.savez_compressed(os.path.join(base, "_hapi_validation.npz"), **npz)
    print("[done] 用时 %.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""同约定复算：证明"本实现"与参考项目差异来自参考项目的同位素丰度重复折算。

参考项目 hitran_slant/lbl.py 在 sT 上又乘了一次天然同位素丰度（HITRAN 的 sw 已含丰度），
本脚本用**本项目的逐线实现**按两种约定各算一遍 24 层逐线透过率：

    conv='correct'  正确约定：sT = sw·(q296/qT)·boltz·stim
    conv='ref'      参考约定：sT 再乘一次天然丰度（复现参考项目 lbl.py）

比较对象：hitran_slant/slant_spectrum.npz（24 层、0.01 cm⁻¹ 网格、USSA76 廓线）。
输出：00_构建脚本/_download/_sameconv_check.json
"""
import os
import sys
import json
import time
import multiprocessing as mp

import numpy as np

PROJ = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
REF = r"F:\DeepSeek工作区\hitran_slant"
BOOT = os.path.join(PROJ, "00_构建脚本")
sys.path.insert(0, BOOT)
import build_xsect as BX
import hapi

BANDS = {"MWIR": (3.7, 4.8), "LWIR": (8.0, 12.0)}
SPECIES = {"H2O": 1, "CO2": 2, "CH4": 6}
T_REF_K = 293.15
C2 = 1.438776877


class LinesConv(BX.Lines):
    """在参考物理基础上返回正确约定与参考约定两种截面。"""

    def sigma_both(self, T, p_atm, grid, step, qT_iso):
        ng = grid.size
        sig_c = np.zeros(ng)
        sig_r = np.zeros(ng)
        qT = qT_iso[self.iso_map]
        boltz = np.exp(-C2 * self.elower * (1.0 / T - 1.0 / BX.T_REF))
        stim = ((1.0 - np.exp(-C2 * self.nu / T))
                / (1.0 - np.exp(-C2 * self.nu / BX.T_REF)))
        sT = self.sw * (self.q296 / qT) * boltz * stim
        sT_ref = sT * self.abund

        gl = np.maximum((BX.T_REF / T) ** self.nair * self.gair * p_atm, 1.0e-8)
        gd = np.maximum((self.nu / BX.C_CM) * np.sqrt(2.0 * BX.KB * T / self.mass), 1.0e-10)
        nus = self.nu + self.delta * p_atm

        sel = (nus + self.half > grid[0]) & (nus - self.half < grid[-1])
        nus, gl, gd = nus[sel], gl[sel], gd[sel]
        sT, sT_ref = sT[sel], sT_ref[sel]
        half, coarse = self.half[sel], self.coarse[sel]
        g0 = grid[0]
        for i in range(nus.size):
            c = nus[i]
            lo = int((c - half[i] - g0) / step)
            hi = int((c + half[i] - g0) / step) + 2
            lo = max(lo, 0)
            hi = min(hi, ng)
            if hi <= lo:
                continue
            y = gl[i] / gd[i]
            if coarse[i]:
                xs = grid[slice(lo, hi, BX.COARSE_FACTOR)]
                f = hapi_symbolic_wofz((xs - c) / gd[i] + 1j * y) * (1.0 / (gd[i] * np.sqrt(np.pi)))
                prof = np.interp(grid[lo:hi], xs, f.real)
                sig_c[lo:hi] += sT[i] * prof
                sig_r[lo:hi] += sT_ref[i] * prof
            else:
                f = hapi_symbolic_wofz((grid[lo:hi] - c) / gd[i] + 1j * y) * (1.0 / (gd[i] * np.sqrt(np.pi)))
                sig_c[lo:hi] += sT[i] * f.real
                sig_r[lo:hi] += sT_ref[i] * f.real
        return np.maximum(sig_c, 0.0), np.maximum(sig_r, 0.0)


from scipy.special import wofz as hapi_symbolic_wofz


def load_layers():
    d = np.genfromtxt(os.path.join(REF, "output", "path_layers.csv"),
                      delimiter=",", names=True)
    return dict(T=d["T_K"], p=d["p_hPa"] / 1013.25, ds_cm=d["slant_len_km"] * 1e5,
                n={"H2O": d["n_H2O_cm3"], "CO2": d["n_CO2_cm3"], "CH4": d["n_CH4_cm3"]})


_LINES = {}


def work(task):
    sp, band, i, T, p, ds, n = task
    lo, hi = BANDS[band]
    nu = np.arange(1e4 / hi, 1e4 / lo + BX.STEP_CM * 0.5, BX.STEP_CM)
    if sp not in _LINES:
        _LINES[sp] = LinesConv(os.path.join(REF, "lines", sp + ".npz"),
                               SPECIES[sp], hapi.ISO, hapi.partitionSum)
    L = _LINES[sp]
    qT = np.array([hapi.partitionSum(L.M, iso, T) for iso in L.iso_uniq])
    sc, sr = L.sigma_both(T, p, nu, BX.STEP_CM, qT)
    return sp, band, i, nu.size, sc * n * ds, sr * n * ds


def band_weights(lam):
    lam_m = lam * 1e-6
    x = 6.62607015e-34 * 2.99792458e8 / (lam_m * 1.380649e-23 * T_REF_K)
    B = 2 * 6.62607015e-34 * 2.99792458e8 ** 2 / lam_m ** 5 / np.expm1(x) * 1e-6
    w = B * x * np.exp(x) / np.expm1(x) / T_REF_K * np.abs(np.gradient(lam))
    return w / w.sum()


def main():
    t0 = time.time()
    layers = load_layers()
    nL = len(layers["T"])
    tasks = [(sp, band, i, layers["T"][i], layers["p"][i], layers["ds_cm"][i],
              layers["n"][sp][i])
             for band in BANDS for sp in SPECIES for i in range(nL)]
    print("[plan] %d 个（物种×波段×层）任务" % len(tasks), flush=True)
    tau_c = {b: {sp: None for sp in SPECIES} for b in BANDS}
    tau_r = {b: {sp: None for sp in SPECIES} for b in BANDS}
    done = 0
    with mp.Pool(3) as pool:
        for sp, band, i, nn, tc, tr in pool.imap_unordered(work, tasks):
            if tau_c[band][sp] is None:
                tau_c[band][sp] = np.zeros(nn)
                tau_r[band][sp] = np.zeros(nn)
            tau_c[band][sp] += tc
            tau_r[band][sp] += tr
            done += 1
            if done % 24 == 0 or done == len(tasks):
                print("[progress %d/%d] (%.0fs)" % (done, len(tasks), time.time() - t0),
                      flush=True)

    ref = np.load(os.path.join(REF, "slant_spectrum.npz"))
    nu_ref = np.asarray(ref["grid"], float)
    lam_ref = nus = 1e4 / nu_ref
    o = np.argsort(lam_ref)
    lam_ref = lam_ref[o]
    tr_ref = {k: np.asarray(ref[k], float)[o] for k in ("tr_H2O", "tr_CO2", "tr_CH4")}

    out = {}
    spectra = {}
    for band, (lo, hi) in BANDS.items():
        lam = (1e4 / np.arange(1e4 / hi, 1e4 / lo + BX.STEP_CM * 0.5, BX.STEP_CM))[::-1]
        w = band_weights(lam)
        m = (lam >= lo) & (lam <= hi)
        mr = (lam_ref >= lo) & (lam_ref <= hi)
        wr = band_weights(lam_ref[mr])
        row = {}
        for sp in SPECIES:
            t_ref = float(np.sum(wr * tr_ref["tr_" + sp][mr]))
            # tau 数组按 ν 升序排列，lam 为 λ 升序（与 tau 反序），统一到 λ 升序
            t_c = float(np.sum(w * np.exp(-tau_c[band][sp])[::-1][m]))
            t_r = float(np.sum(w * np.exp(-tau_r[band][sp])[::-1][m]))
            row[sp] = dict(
                ref=t_ref, correct=t_c, ref_convention=t_r,
                reldiff_correct_vs_ref_pct=100 * (t_c / t_ref - 1),
                reldiff_refconv_vs_ref_pct=100 * (t_r / t_ref - 1),
                bug_effect_pct=100 * (t_c / t_r - 1),
            )
            print("%s %-3s 参考 %.4f | 同约定复算 %.4f (%+.2f%%) | 正确约定 %.4f (%+.2f%%)"
                  % (band, sp, t_ref, t_r, row[sp]["reldiff_refconv_vs_ref_pct"],
                     t_c, row[sp]["reldiff_correct_vs_ref_pct"]), flush=True)
            spectra["%s_%s_ref" % (band, sp)] = np.interp(
                lam[m], lam_ref, tr_ref["tr_" + sp])
            spectra["%s_%s_correct" % (band, sp)] = np.exp(-tau_c[band][sp])[::-1][m]
            spectra["%s_%s_refconv" % (band, sp)] = np.exp(-tau_r[band][sp])[::-1][m]
        spectra["%s_lam" % band] = lam[m]
        out[band] = row

    # 总透过率（三气体乘积）对照，供 Validation 图
    for band in BANDS:
        lam = spectra["%s_lam" % band]
        spectra["%s_total_correct" % band] = np.prod(
            [spectra["%s_%s_correct" % (band, sp)] for sp in SPECIES], axis=0)
        spectra["%s_total_refconv" % band] = np.prod(
            [spectra["%s_%s_refconv" % (band, sp)] for sp in SPECIES], axis=0)
        spectra["%s_total_ref" % band] = np.prod(
            [spectra["%s_%s_ref" % (band, sp)] for sp in SPECIES], axis=0)
    np.savez_compressed(os.path.join(BOOT, "_download", "_sameconv_spectra.npz"),
                        **spectra)

    path = os.path.join(BOOT, "_download", "_sameconv_check.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", path, " 用时 %.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()

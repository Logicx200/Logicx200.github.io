# -*- coding: utf-8 -*-
"""自检：多气压 × 多温度截面 vs 参考项目 hitran_slant 逐层逐线结果。

方法
----
读取参考项目 output/path_layers.csv 的 24 层 (T, p, n_H2O, n_CO2, n_CH4, ds)，
用本项目的 07_光谱数据/xsect_*.npz 截面做 (T 线性, log p 线性) 双线性插值，
逐层累加光学厚度 τ = Σ σ(T_i, p_i)·n_i·ds_i，得到 τ_H2O/τ_CO2/τ_CH4；
再与 hitran_slant/slant_spectrum.npz 的 tr_H2O/tr_CO2/tr_CH4 比较，
在两个业务波段 3.7–4.8 μm、8–12 μm 上做 dB/dT 加权平均（T_ref = 293.15 K）。

同时给出仅用 P=1 atm 节点（无气压插值）的结果，用于量化"1 atm 近似"的影响。
"""
import os
import json
import numpy as np

PROJ = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
REF = r"F:\DeepSeek工作区\hitran_slant"
SPEC = os.path.join(PROJ, "07_光谱数据")

BANDS = {"MWIR": (3.7, 4.8), "LWIR": (8.0, 12.0)}
T_REF_K = 293.15
C2 = 14387.76877          # μm·K
C1 = 1.191042972e8        # W·μm⁴/(m²·sr)
H_PLANCK, C_LIGHT, K_B = 6.62607015e-34, 2.99792458e8, 1.380649e-23


def planck(lam_um, T):
    lam = np.asarray(lam_um, float) * 1e-6
    x = H_PLANCK * C_LIGHT / (lam * K_B * T)
    return 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / np.expm1(x) * 1e-6


def d_planck_dT(lam_um, T):
    lam = np.asarray(lam_um, float) * 1e-6
    x = H_PLANCK * C_LIGHT / (lam * K_B * T)
    B = 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / np.expm1(x) * 1e-6
    return B * x * np.exp(x) / np.expm1(x) / T


def band_weights(lam_um, T_ref=T_REF_K):
    w = d_planck_dT(lam_um, T_ref)
    dlam = np.abs(np.gradient(np.asarray(lam_um, float)))
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0) * dlam
    return w / w.sum()


def load_layers():
    d = np.genfromtxt(os.path.join(REF, "output", "path_layers.csv"),
                      delimiter=",", names=True)
    return dict(T=d["T_K"], p=d["p_hPa"] / 1013.25, ds_cm=d["slant_len_km"] * 1e5,
                n_H2O=d["n_H2O_cm3"], n_CO2=d["n_CO2_cm3"], n_CH4=d["n_CH4_cm3"])


def load_xsect(band):
    path = os.path.join(SPEC, "xsect_%s.npz" % band.lower())
    with np.load(path, allow_pickle=False) as d:
        nu = np.asarray(d["nu"], float)
        out = {}
        for sp in ("H2O", "CO2", "CH4"):
            keys = [k for k in d.files if k.startswith(sp + "_T")]
            temps = sorted({float(k.split("_T")[1].split("_P")[0]) for k in keys})
            press = sorted({float(k.split("_P")[1]) for k in keys})
            arr = np.empty((len(temps), len(press), nu.size))
            for i, T in enumerate(temps):
                for j, P in enumerate(press):
                    k = "%s_T%d_P%.2f" % (sp, int(T), P)
                    arr[i, j] = np.asarray(d[k], float)
            out[sp] = (np.array(temps), np.array(press), arr)
    return nu, out


def interp_sigma(spec, T, p, use_pressure=True):
    """(T 线性, log p 线性) 双线性插值；use_pressure=False 时用 P=1 atm 节点。"""
    temps, press, arr = spec
    Tc = float(np.clip(T, temps[0], temps[-1]))
    i = int(np.clip(np.searchsorted(temps, Tc) - 1, 0, len(temps) - 2))
    ft = (Tc - temps[i]) / max(temps[i + 1] - temps[i], 1e-9)
    if use_pressure and len(press) > 1:
        pc = float(np.clip(p, press.min(), press.max()))
        lp = np.log(press)
        j = int(np.clip(np.searchsorted(lp, np.log(pc)) - 1, 0, len(press) - 2))
        fp = (np.log(pc) - lp[j]) / max(lp[j + 1] - lp[j], 1e-9)
        return ((1 - ft) * (1 - fp) * arr[i, j] + (1 - ft) * fp * arr[i, j + 1]
                + ft * (1 - fp) * arr[i + 1, j] + ft * fp * arr[i + 1, j + 1])
    j1 = int(np.argmin(np.abs(press - 1.0)))
    return (1 - ft) * arr[i, j1] + ft * arr[i + 1, j1]


def tau_spectrum(band, layers, use_pressure=True):
    nu, specs = load_xsect(band)
    lam = (1e4 / nu)[::-1]                     # λ 升序（与 nu 反序）
    tau = {sp: np.zeros(nu.size) for sp in specs}
    for i in range(len(layers["T"])):
        for sp in specs:
            sig = interp_sigma(specs[sp], layers["T"][i], layers["p"][i], use_pressure)
            tau[sp] += sig * layers["n_" + sp][i] * layers["ds_cm"][i]
    # 统一到 λ 升序，避免与掩膜/权重错位
    tau = {sp: tau[sp][::-1] for sp in tau}
    return lam, tau, nu


def main():
    layers = load_layers()
    ref = np.load(os.path.join(REF, "slant_spectrum.npz"))
    nu_ref = np.asarray(ref["grid"], float)
    lam_ref = 1e4 / nu_ref
    o = np.argsort(lam_ref)
    lam_ref = lam_ref[o]
    tr_ref = {k: np.asarray(ref[k], float)[o] for k in ("tr_H2O", "tr_CO2", "tr_CH4", "tr_total")}

    report = {}
    for band, (lo, hi) in BANDS.items():
        lam, tau, nu = tau_spectrum(band, layers, True)
        _, tau1, _ = tau_spectrum(band, layers, False)
        m = (lam >= lo) & (lam <= hi)
        w = band_weights(lam[m])
        mr = (lam_ref >= lo) & (lam_ref <= hi)
        wr = band_weights(lam_ref[mr])
        row = {}
        for sp in ("H2O", "CO2", "CH4"):
            t_multi = np.exp(-tau[sp])
            t_1atm = np.exp(-tau1[sp])
            t_ref = tr_ref["tr_" + sp][mr]
            vals = {
                "ref": float(np.sum(wr * t_ref)),
                "multiP": float(np.sum(w * t_multi[m])),
                "P1atm": float(np.sum(w * t_1atm[m])),
            }
            vals["reldiff_multiP_vs_ref_pct"] = 100 * (vals["multiP"] / vals["ref"] - 1)
            vals["reldiff_P1atm_vs_ref_pct"] = 100 * (vals["P1atm"] / vals["ref"] - 1)
            vals["reldiff_P1atm_vs_multiP_pct"] = 100 * (vals["P1atm"] / vals["multiP"] - 1)
            row[sp] = vals
            print("%s %-3s 参考 %.4f | 多气压 %.4f (%+.2f%%) | 仅1atm %.4f (%+.2f%%)"
                  " | 1atm-多气压 %+.2f%%"
                  % (band, sp, vals["ref"], vals["multiP"],
                     vals["reldiff_multiP_vs_ref_pct"], vals["P1atm"],
                     vals["reldiff_P1atm_vs_ref_pct"],
                     vals["reldiff_P1atm_vs_multiP_pct"]))
        tot_multi = np.prod([np.exp(-tau[sp]) for sp in ("H2O", "CO2", "CH4")], axis=0)
        row["total"] = dict(multiP=float(np.sum(w * tot_multi[m])))
        report[band] = row

    out = os.path.join(PROJ, "00_构建脚本", "_download", "_selfcheck_xsect.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("wrote", out)


if __name__ == "__main__":
    main()

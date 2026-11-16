# -*- coding: utf-8 -*-
"""生成 06_校验/Validation_大气模型对比.png

内容
----
(a)(b) 本模型线吸收（H2O+CO2+CH4，气溶胶/散射关闭）与参考项目同几何结果对比：
        本模型（正确丰度约定）、参考约定复算（本实现按参考项目同一丰度约定）、
        参考项目谱（slant_spectrum.npz）；标题标注 dB/dT 加权波段平均透过率。
(c)    HAPI 独立实现 vs 本实现：280 K、1 atm 下强吸收点逐点截面散点（log-log，±5% 引导线）。
(d)    相对差汇总：本模型 vs 参考同约定复算、本模型 vs HAPI 窗口加权、
        本模型（正确约定）vs 参考谱。
"""
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

PROJ = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
BOOT = os.path.join(PROJ, "00_构建脚本", "_download")
OUT = os.path.join(PROJ, "06_校验", "Validation_大气模型对比.png")
BAND_LABEL = {"MWIR": "中波 3.7–4.8 μm", "LWIR": "长波 8.0–12.0 μm"}
SPEC_COLORS = {"H2O": "#1f6fd0", "CO2": "#d62728", "CH4": "#2ca02c"}


def setup():
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False, "font.size": 10, "axes.linewidth": 0.9,
        "savefig.dpi": 300,
    })


def nu_axes(ax, lo_um, hi_um, nticks=7):
    nu_lo, nu_hi = 1e4 / hi_um, 1e4 / lo_um
    ax.set_xlim(nu_lo, nu_hi)
    ax.set_xticks(np.linspace(nu_lo, nu_hi, nticks))
    ax.xaxis.set_minor_locator(AutoMinorLocator(4))
    ax.set_xlabel("波数 (cm$^{-1}$)")
    sec = ax.secondary_xaxis(
        "top", functions=(lambda v: 1e4 / np.maximum(v, 1e-9),
                          lambda lam: 1e4 / np.maximum(lam, 1e-9)))
    ticks = np.linspace(lo_um, hi_um, 6)
    sec.set_xticks(ticks)
    sec.set_xticklabels(["%.2f" % t for t in ticks], fontsize=8.5)
    sec.set_xlabel("波长 (μm)", fontsize=9.5, labelpad=2)


def rev(lam, y):
    """λ 升序 → ν 升序。"""
    return (1e4 / np.asarray(lam, float))[::-1], np.asarray(y, float)[::-1]


def main():
    setup()
    sp = np.load(os.path.join(BOOT, "_sameconv_spectra.npz"))
    same = json.load(open(os.path.join(BOOT, "_sameconv_check.json"), encoding="utf-8"))
    hapi_rows = json.load(open(os.path.join(BOOT, "_hapi_validation.json"), encoding="utf-8"))
    hd = np.load(os.path.join(BOOT, "_hapi_validation.npz"))

    fig = plt.figure(figsize=(15.0, 11.4))
    gs = fig.add_gridspec(2, 2, hspace=0.58, wspace=0.17,
                          left=0.055, right=0.985, top=0.90, bottom=0.07)
    limits = {"MWIR": (3.7, 4.8), "LWIR": (8.0, 12.0)}

    for col, band in enumerate(("MWIR", "LWIR")):
        ax = fig.add_subplot(gs[0, col])
        lam = np.asarray(sp["%s_lam" % band], float)
        x, y_c = rev(lam, sp["%s_total_correct" % band])
        _, y_rc = rev(lam, sp["%s_total_refconv" % band])
        _, y_ref = rev(lam, sp["%s_total_ref" % band])
        ax.plot(x, y_ref, color="#999999", lw=0.8, alpha=0.95,
                label="参考项目谱（$\\bar T$=%.3f）" % np.mean(y_ref))
        ax.plot(x, y_rc, color="#d62728", lw=0.9, ls="--",
                label="参考约定复算（$\\bar T$=%.3f）" % np.mean(y_rc))
        ax.plot(x, y_c, color="#111111", lw=1.0,
                label="本模型（$\\bar T$=%.3f）" % np.mean(y_c))
        ax.set_ylim(0, 1.04)
        ax.set_ylabel("线吸收斜程透过率  $T$")
        ax.grid(alpha=0.22, lw=0.5)
        lo, hi = limits[band]
        nu_axes(ax, lo, hi)
        ax.text(0.012, 0.955,
                "%s%s：本模型 vs 参考项目（8 km 平台 / 20 km 地面，斜距 21.55 km）"
                % ("(a) " if band == "MWIR" else "(b) ", BAND_LABEL[band]),
                transform=ax.transAxes, fontsize=9.2, va="top",
                bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=1.6))
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.145), ncol=3,
                  fontsize=8.2, frameon=False, handlelength=2.0,
                  columnspacing=1.4, handletextpad=0.5)
        if band == "MWIR":
            ax.annotate("CO$_2$ 4.3 μm 带：参考项目把 HITRAN 线强\n重复乘天然丰度，"
                        "13CO$_2$（丰度 1.1%）偏弱约 90 倍",
                        xy=(2349.0, 0.06), xytext=(2470.0, 0.42), fontsize=8.2,
                        bbox=dict(facecolor="#fff6d5", alpha=0.9, edgecolor="#cc9900",
                                  lw=0.6, pad=2.5),
                        arrowprops=dict(arrowstyle="->", lw=0.8, color="#886600"))
        else:
            ax.annotate("O$_3$ 9.6 μm", xy=(1042.0, 0.15), xytext=(1042.0, 0.55),
                        fontsize=8.2, ha="center",
                        arrowprops=dict(arrowstyle="-", lw=0.7, color="#777777"))

    # -------- (c) HAPI 独立实现 vs 本实现（强吸收点） --------
    axs = fig.add_subplot(gs[1, 0])
    markers = {"MWIR": "o", "LWIR": "s"}
    all_rel = []
    for row in hapi_rows:
        key = "%s_%s" % (row["species"], row["band"])
        nu = np.asarray(hd[key + "_nu"], float)
        ch = np.asarray(hd[key + "_hapi"], float)
        co = np.asarray(hd[key + "_ours"], float)
        strong = ch > max(1e-23, 0.01 * float(ch.max()))
        # 抽稀散点，避免过密
        idx = np.where(strong)[0]
        if idx.size > 1400:
            idx = idx[:: max(1, idx.size // 1400)]
        axs.scatter(ch[idx], co[idx], s=3.0, alpha=0.55,
                    color=SPEC_COLORS[row["species"]],
                    marker=markers[row["band"]],
                    label="%s %s" % (row["species"], "中波" if row["band"] == "MWIR" else "长波"))
        rel = (co[strong] - ch[strong]) / np.maximum(ch[strong], 1e-300)
        all_rel.extend(np.abs(rel).tolist())
    vmin, vmax = 1e-24, 2e-17
    axs.plot([vmin, vmax], [vmin, vmax], color="#111111", lw=0.9)
    for f in (1.05, 0.95):
        axs.plot([vmin, vmax], [vmin * f, vmax * f], color="#d62728", lw=0.7, ls="--")
    axs.set_xscale("log")
    axs.set_yscale("log")
    axs.set_xlim(vmin, vmax)
    axs.set_ylim(vmin, vmax)
    axs.set_xlabel("HAPI 独立实现截面 (cm$^2$/molecule)")
    axs.set_ylabel("本实现截面 (cm$^2$/molecule)")
    axs.grid(alpha=0.22, lw=0.5, which="both")
    axs.text(0.03, 0.955, "(c) 与 HAPI 独立实现逐点对比（280 K, 1 atm，强吸收点）",
             transform=axs.transAxes, fontsize=9.8, fontweight="bold", va="top")
    axs.text(0.03, 0.885,
             "强吸收点 |相对差|：中位 %.2f%%，p90 %.2f%%（红线 ±5%%）\n"
             "HAPI：absorptionCoefficient_Voigt，Diluent=air，HITRAN2020"
             % (100 * np.median(all_rel), 100 * np.percentile(all_rel, 90)),
             transform=axs.transAxes, fontsize=8.2, va="top",
             bbox=dict(facecolor="white", alpha=0.85, edgecolor="#bbbbbb", lw=0.5, pad=3))
    axs.legend(loc="lower right", fontsize=7.8, frameon=True, framealpha=0.75,
               markerscale=2.2, ncol=2)

    # -------- (d) 相对差汇总 --------
    axb = fig.add_subplot(gs[1, 1])
    groups = []
    s1, s2, s3 = [], [], []
    for band in ("MWIR", "LWIR"):
        for spc in ("H2O", "CO2", "CH4"):
            groups.append("%s-%s" % ("中波" if band == "MWIR" else "长波", spc))
            s1.append(same[band][spc]["reldiff_refconv_vs_ref_pct"])
            s3.append(same[band][spc]["reldiff_correct_vs_ref_pct"])
            row = next(r for r in hapi_rows
                       if r["species"] == spc and r["band"] == band)
            s2.append(row["bandavg_sigma_reldiff_pct"])
    x = np.arange(len(groups))
    w = 0.26
    axb.bar(x - w, s1, w, color="#2ca02c", alpha=0.85, label="本模型 vs 参考同约定复算")
    axb.bar(x, s2, w, color="#1f6fd0", alpha=0.85, label="本模型 vs HAPI（窗口加权）")
    axb.bar(x + w, s3, w, color="#d62728", alpha=0.85,
            label="本模型（正确约定）vs 参考谱")
    axb.axhline(0, color="#333333", lw=0.8)
    for y, txt in ((2.0, "2%"), (-2.0, "-2%")):
        axb.axhline(y, color="#888888", lw=0.7, ls=":")
    axb.set_xticks(x)
    axb.set_xticklabels(groups, rotation=18, fontsize=8.4, ha="right")
    axb.set_ylabel("波段平均相对差 (%)")
    axb.grid(alpha=0.22, lw=0.5, axis="y")
    axb.set_ylim(-12.5, 4.5)
    axb.text(0.03, 0.965, "(d) 相对差汇总（绿/蓝 <2% 为通过；红为参考项目丰度重复折算所致）",
             transform=axb.transAxes, fontsize=9.2, fontweight="bold", va="top")
    axb.legend(loc="lower left", fontsize=7.8, frameon=True, framealpha=0.8)

    fig.suptitle("大气模型与光谱数据校验：本模型 vs HAPI 独立实现 / 参考项目同几何结果",
                 fontsize=13, y=0.985)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("[validation-fig] →", OUT)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
irrecog.plots_atmo —— 图03：斜程大气光谱透过率（精简版，1 行 × 2 列）

每个面板一个波段（左 MWIR 3.7–4.8 μm、右 LWIR 8.0–12.0 μm），只画 4 条
**总透过率**曲线（4 种气候工况），基线黑线并在其下方填充浅灰：

    基线（AOD 0.587, PWV 1.28 cm）
    清洁干燥（AOD 0.05, PWV 0.4 cm）
    湿热带（PWV 5.0 cm）
    强沙尘（AOD 4.0, α=0.25）

双轴：下轴波数 cm⁻¹，上轴波长 μm；整图共用底部单一图例；仅保留必要的
吸收带/线标注（白底小框，y 位置错开）。

对外接口：``fig03(outdir) -> png 路径``（plots.make_all 调用）。
"""

import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator

from . import atmosphere as A

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "font.size": 10.0,
    "axes.linewidth": 0.9,
    "savefig.dpi": 300,
})

# 4 种气候工况：(图例名, Atmo)
_SCENARIOS = [
    ("基线", A.Atmo()),
    ("清洁干燥", A.Atmo(aod550=0.05, pwv_cm=0.4)),
    ("湿热带", A.Atmo(pwv_cm=5.0)),
    ("强沙尘", A.Atmo(aod550=4.0, alpha=0.25)),
]
_COLORS = ["#111111", "#1f9e4c", "#1f6fd0", "#c46a13"]
_STYLES = ["-", "--", "-.", ":"]
_WIDTHS = [0.95, 0.62, 0.62, 0.62]

_BANDS = ("MWIR", "LWIR")
_BAND_CN = {"MWIR": "MWIR 3.7–4.8 μm", "LWIR": "LWIR 8.0–12.0 μm"}
_XLIM = {"MWIR": (1e4 / 4.8, 1e4 / 3.7), "LWIR": (1e4 / 12.0, 1e4 / 8.0)}
# 必要标注：(波数 cm⁻¹, 文本, 文字纵坐标)
_FEATURES = {
    "MWIR": [(2347.0, "CO$_2$ 4.3 μm", 0.90),
             (2195.0, "N$_2$O / CO 4.5–4.6 μm", 0.74),
             (2600.0, "H$_2$O 线", 0.60)],
    "LWIR": [(960.0, "CO$_2$ 10.4 μm", 0.90),
             (1042.0, "O$_3$ 9.6 μm", 0.74),
             (1175.0, "H$_2$O 线", 0.60)],
}
R_GROUND_KM, Z_SENSOR_M, Z_TARGET_M = 20.0, 8000.0, 0.0


def _to_nu(lam_um, y):
    """λ 升序 → ν 升序（下轴用波数）。"""
    lam = np.asarray(lam_um, float)
    return (1e4 / lam)[::-1], np.asarray(y, float)[::-1]


def _nu_axis(ax, band):
    lo, hi = _XLIM[band]
    ax.set_xlim(lo, hi)
    ax.set_xticks(np.linspace(lo, hi, 7))
    ax.xaxis.set_minor_locator(AutoMinorLocator(4))
    ax.set_xlabel("波数 (cm$^{-1}$)")
    for t in ax.get_xticklabels():
        t.set_fontsize(8.5)


def _top_wavelength(ax, band):
    lo, hi = _XLIM[band]
    sec = ax.secondary_xaxis(
        "top", functions=(lambda v: 1e4 / np.maximum(v, 1e-9),
                          lambda lam: 1e4 / np.maximum(lam, 1e-9)))
    lam_lo, lam_hi = 1e4 / hi, 1e4 / lo
    ticks = np.linspace(lam_lo, lam_hi, 6)
    sec.set_xticks(ticks)
    sec.set_xticklabels(["%.2f" % t for t in ticks], fontsize=8.5)
    sec.set_xlabel("波长 (μm)", fontsize=9.0, labelpad=1)


def fig03(outdir, r_ground_km=R_GROUND_KM, z_sensor_m=Z_SENSOR_M,
          z_target_m=Z_TARGET_M, dpi=300):
    """绘制精简版图03（1 行 × 2 列），返回 PNG 路径。"""
    os.makedirs(outdir, exist_ok=True)

    states = {}
    for band in _BANDS:
        for i, (_, atmo) in enumerate(_SCENARIOS):
            states[(band, i)] = A.spectral_state(
                atmo, band, r_ground_km, z_target_m, z_sensor_m,
                with_components=False)

    fig, axes = plt.subplots(1, 2, figsize=(14.2, 6.3))
    fig.subplots_adjust(left=0.062, right=0.988, bottom=0.225,
                        top=0.795, wspace=0.13)

    tau_bar = {band: states[(band, 0)]["tau_band"] for band in _BANDS}

    for col, band in enumerate(_BANDS):
        ax = axes[col]
        for i, (name, _) in enumerate(_SCENARIOS):
            st = states[(band, i)]
            nu, y = _to_nu(st["lam_um"], st["tau_lam"])
            if i == 0:
                ax.fill_between(nu, 0.0, y, color="#9aa4b0", alpha=0.30, lw=0)
            ax.plot(nu, y, color=_COLORS[i], lw=_WIDTHS[i], ls=_STYLES[i],
                    alpha=0.95, solid_capstyle="butt")
        ax.set_ylim(0.0, 1.04)
        ax.set_yticks(np.linspace(0.0, 1.0, 6))
        ax.set_yticklabels(["%.1f" % v for v in np.linspace(0.0, 1.0, 6)],
                           fontsize=8.5)
        if col == 0:
            ax.set_ylabel("斜程总透过率  $T$")
        else:
            ax.tick_params(labelleft=False)
        ax.grid(alpha=0.20, lw=0.5)
        _nu_axis(ax, band)
        _top_wavelength(ax, band)
        ax.set_title("(%s) %s（斜距 %.2f km）"
                     % ("a" if col == 0 else "b", _BAND_CN[band],
                        states[(band, 0)]["r_slant_km"]),
                     fontsize=10.5, pad=9)
        # 必要吸收带/线标注：白底小框，y 位置错开
        for nu0, txt, ytxt in _FEATURES[band]:
            ax.text(nu0, ytxt, txt, fontsize=7.8, ha="center", va="center",
                    color="#222222", zorder=9,
                    bbox=dict(facecolor="white", alpha=0.82,
                              edgecolor="#d0d0d0", lw=0.5, pad=1.8))

    # 整图共用底部单一图例
    handles = [Line2D([0], [0], color=_COLORS[i], lw=max(_WIDTHS[i], 0.8),
                      ls=_STYLES[i]) for i in range(len(_SCENARIOS))]
    labels = ["%s（波段平均 $\\bar\\tau$：MWIR %.3f / LWIR %.3f）"
              % (_SCENARIOS[0][0], tau_bar["MWIR"], tau_bar["LWIR"])]
    labels += [name for name, _ in _SCENARIOS[1:]]
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.015),
               ncol=4, frameon=False, fontsize=9.2,
               handlelength=2.8, columnspacing=2.0, handletextpad=0.6)

    fig.suptitle("图 3 斜程大气光谱透过率（8 km 平台 → 20 km 地面，"
                 "斜距 21.55 km；波段平均按 dB/dT 加权）",
                 fontsize=12.8, y=1.035)

    png = os.path.join(outdir, "图03_斜程大气光谱透过率.png")
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print("[fig03] →", png, flush=True)
    return png


if __name__ == "__main__":
    import sys
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, "02_图表")
    fig03(out)

# -*- coding: utf-8 -*-
"""
复杂大气红外探测仿真 —— 参数相图示意脚本（仅用于方案讨论，不是最终仿真结果）

用简化模型演示"环境参数 -> 效果指标"的二维相图形态：
  1) 大气衰减相图：MOR x alpha -> 波段透过率 tau
  2) 系统能力相图：MOR x 距离 R -> 探测概率 Pd
  3) 分辨能力相图：Cn2 x 距离 R -> 可分辨周期数 N

模型假设（示意用）：
  - beta(lambda) = 3.912/MOR * (0.55/lambda)^alpha            [km^-1]
  - tau_band(R) = 波段内按 300 K 黑体 dL/dT 加权平均的 exp(-beta*R)
  - 温差近似: dT_app = tau_band * dT
  - 几何周期数: N_geo = D_t / (R * IFOV)
  - 湍流: r0 = 0.185 * lambda^(6/5) * (Cn2*L)^(-3/5)，
          有效 IFOV = sqrt(IFOV^2 + (lambda/r0)^2)
  - 简化双判据: P_d = min(P_res, P_con)
      P_res = (N/N50)^E / (1+(N/N50)^E)
      P_con = (SNR/SNR50)^E / (1+(SNR/SNR50)^E), SNR = dT_app/NETD
正式方案应替换为 TTP/MRTD 链与 libRadtran/COSSIM 结果。

输出: figures/phase_atmo.png, figures/phase_capability.png, figures/phase_turbulence.png
"""

import os
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# ----------------------------- 常量与基线参数 -----------------------------
H = 6.62607015e-34
C = 2.99792458e8
K = 1.380649e-23
C2 = H * C / K  # m*K

MOR_RANGE = (0.5, 30.0)
ALPHA_RANGE = (0.0, 2.0)
R_RANGE = (1.0, 10.0)       # km
CN2_RANGE = (1e-16, 1e-12)  # m^(-2/3)

NETD = 0.05      # K（示意用非制冷型；正式方案可换 30 mK 制冷型）
IFOV = 0.06e-3   # rad (15 um / 250 mm)
D_T = 2.3        # m 目标临界尺寸
N50, E = 8.0, 2.0
SNR50 = 3.0
DT_BASE = 3.0    # K（示意用低对比目标）
BANDS = {"MWIR (3-5 um)": (3.0, 5.0, 4.0), "LWIR (8-12 um)": (8.0, 12.0, 10.0)}


def planck_dBdT(lam_um, T=300.0):
    lam = np.asarray(lam_um) * 1e-6
    x = C2 / (lam * T)
    B = 2 * H * C**2 / lam**5 / np.expm1(x)
    return B * x / T * np.exp(x) / np.expm1(x)


def tau_band(mor, alpha, lam_lo, lam_hi, r_km, n_lam=81):
    lam = np.linspace(lam_lo, lam_hi, n_lam)
    w = planck_dBdT(lam)
    w = w / w.sum()
    b = (3.912 / mor)[..., None] * (0.55 / lam) ** alpha[..., None]  # km^-1
    tau = np.exp(-b * np.asarray(r_km)[..., None])
    return (tau * w).sum(axis=-1)


def r0_fried(cn2, r_km, lam_um):
    lam = lam_um * 1e-6
    L = r_km * 1e3
    return 0.185 * lam ** 1.2 * (cn2 * L) ** (-0.6)


def p_logistic(ratio):
    r = np.maximum(ratio, 1e-9)
    return r**E / (1 + r**E)


def grid(mor=None, alpha=None, r=None, cn2=None):
    if mor is not None and alpha is not None:
        return np.meshgrid(mor, alpha, indexing="ij")
    if mor is not None and r is not None:
        return np.meshgrid(mor, r, indexing="ij")
    if cn2 is not None and r is not None:
        return np.meshgrid(cn2, r, indexing="ij")
    raise ValueError


def weather_boxes(ax):
    """在 (MOR, alpha) 平面标注典型天气区域（示意）。"""
    boxes = [
        ("雾", 0.5, 1.0, 0.0, 0.18, "#4C72B0"),
        ("霾/城市", 1.0, 10.0, 1.0, 1.6, "#DD8452"),
        ("沙尘", 2.0, 10.0, 0.2, 0.5, "#C44E52"),
        ("雨", 5.0, 20.0, 0.0, 0.08, "#55A868"),
        ("晴空乡村", 15.0, 30.0, 1.2, 1.5, "#8172B3"),
    ]
    for name, m0, m1, a0, a1, color in boxes:
        ax.add_patch(Rectangle((m0, a0), m1 - m0, a1 - a0 + 0.02,
                               fill=False, edgecolor=color, lw=1.4, ls="--"))
        ax.text(m0 * 1.06, min(a1 + 0.08, 1.95), name, color=color, fontsize=8.5)


def fig_atmo(path):
    mor = np.logspace(np.log10(MOR_RANGE[0]), np.log10(MOR_RANGE[1]), 161)
    alpha = np.linspace(*ALPHA_RANGE, 141)
    M, A = grid(mor=mor, alpha=alpha)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), constrained_layout=True)
    for ax, (name, (lo, hi, _)) in zip(axes, BANDS.items()):
        T = tau_band(M, A, lo, hi, r_km=5.0)
        im = ax.pcolormesh(mor, alpha, T.T, shading="nearest", cmap="viridis",
                           vmin=0, vmax=1, rasterized=True)
        ax.set_xscale("log")
        ax.set_xlim(*MOR_RANGE)
        ax.set_ylim(*ALPHA_RANGE)
        ax.set_xlabel("能见度 MOR (km，对数轴)")
        ax.set_ylabel("Ångström 指数 α")
        ax.set_title(f"{name} · R = 5 km")
        weather_boxes(ax)
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("波段透过率 τ")
    fig.suptitle("图 1  大气衰减相图（示意：简化模型，非最终结果）", fontsize=11)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_capability(path):
    mor = np.logspace(np.log10(MOR_RANGE[0]), np.log10(MOR_RANGE[1]), 161)
    rr = np.linspace(*R_RANGE, 141)
    M, R = grid(mor=mor, r=rr)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), constrained_layout=True)
    for ax, (name, (lo, hi, lam_mid)) in zip(axes, BANDS.items()):
        T = tau_band(M, np.full_like(M, 1.3), lo, hi, R)
        dt_app = DT_BASE * T
        snr = dt_app / NETD
        r0 = r0_fried(1e-14, R, lam_mid)
        ifov_eff = np.sqrt(IFOV**2 + (lam_mid * 1e-6 / r0) ** 2)
        n_eff = D_T / (R * 1e3 * ifov_eff)
        p = np.minimum(p_logistic(n_eff / N50), p_logistic(snr / SNR50))
        im = ax.pcolormesh(mor, rr, p.T, shading="nearest", cmap="magma",
                           vmin=0, vmax=1, rasterized=True)
        cs = ax.contour(mor, rr, p.T, levels=[0.1, 0.5, 0.9], colors="w",
                        linewidths=[0.8, 1.6, 0.8])
        ax.clabel(cs, fmt="Pd=%.1f", fontsize=8)
        ax.set_xscale("log")
        ax.set_xlim(*MOR_RANGE)
        ax.set_ylim(*R_RANGE)
        ax.set_xlabel("能见度 MOR (km，对数轴)")
        ax.set_ylabel("作用距离 R (km)")
        ax.set_title(f"{name} · ΔT={DT_BASE:.0f} K · NETD={NETD*1000:.0f} mK · Cn²=1e-14")
        cb = fig.colorbar(im, ax=ax, pad=0.02)
        cb.set_label("探测概率 P_d")
    fig.suptitle("图 2  系统能力相图（示意：简化双判据，非最终结果）", fontsize=11)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_turbulence(path):
    cn2 = np.logspace(np.log10(CN2_RANGE[0]), np.log10(CN2_RANGE[1]), 161)
    rr = np.linspace(*R_RANGE, 141)
    Cg, R = grid(cn2=cn2, r=rr)
    lam_mid = 10.0
    r0 = r0_fried(Cg, R, lam_mid)
    ifov_eff = np.sqrt(IFOV**2 + (lam_mid * 1e-6 / r0) ** 2)
    n_eff = D_T / (R * 1e3 * ifov_eff)
    fig, ax = plt.subplots(figsize=(6.4, 4.6), constrained_layout=True)
    im = ax.pcolormesh(cn2, rr, n_eff.T, shading="nearest", cmap="cividis",
                       rasterized=True)
    cs = ax.contour(cn2, rr, n_eff.T, levels=[N50], colors="w", linewidths=1.6)
    ax.clabel(cs, fmt="N = N50 = 8", fontsize=8)
    ax.set_xscale("log")
    ax.set_xlim(*CN2_RANGE)
    ax.set_ylim(*R_RANGE)
    ax.set_xlabel("湍流强度 Cn² (m^(-2/3)，对数轴)")
    ax.set_ylabel("作用距离 R (km)")
    ax.set_title("图 3  湍流分辨相图（LWIR 10 μm，示意）")
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("湍流限制的有效周期数 N")
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs("figures", exist_ok=True)
    fig_atmo("figures/phase_atmo.png")
    fig_capability("figures/phase_capability.png")
    fig_turbulence("figures/phase_turbulence.png")
    print("done: figures/phase_atmo.png, phase_capability.png, phase_turbulence.png")

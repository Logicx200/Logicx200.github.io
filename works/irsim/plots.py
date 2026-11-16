# -*- coding: utf-8 -*-
"""irsim.plots —— 仿真结果图件（中文标注，保存 PNG）。"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import model as m
from . import experiments as ex

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120


def fig_spectra(path, sensor, target):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), constrained_layout=True)
    cases = [
        ("基准 A0 (MWIR)", m.Atmo(23, 1.3, 1.5, 1e-14), "MWIR"),
        ("中等霾 B3 (MWIR)", m.Atmo(5, 1.3, 1.5, 1e-14), "MWIR"),
        ("沙尘 C3 (MWIR)", m.Atmo(4, 0.3, 1.0, 1e-14), "MWIR"),
        ("基准 A0 (LWIR)", m.Atmo(23, 1.3, 1.5, 1e-14), "LWIR"),
        ("中等霾 B3 (LWIR)", m.Atmo(5, 1.3, 1.5, 1e-14), "LWIR"),
        ("浓雾 C1 (LWIR)", m.Atmo(0.8, 0.0, 3.0, 1e-13), "LWIR"),
        ("雨等效 C4 (LWIR)", m.Atmo(8, 0.0, 4.0, 1e-14), "LWIR"),
    ]
    for ax, band in zip(axes, ["MWIR", "LWIR"]):
        lam = m.band_grid(band)
        for name, atmo, b in cases:
            if b != band:
                continue
            beta = m.beta_spectrum(lam, atmo, band)
            tau = np.exp(-beta * 5.0)
            ax.plot(lam, tau, lw=1.6, label=name)
        ax.set_xlabel("波长 (μm)")
        ax.set_ylabel("5 km 水平路径透过率")
        ax.set_title(band)
        ax.set_ylim(0, 1.02)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("图 1  典型工况的波段透过率谱（简化大气模型）", fontsize=11)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_phase_R50(path, sensor, target, mor_grid, alpha_grid, Z, band,
                  levels=(8.0,), task_label="探测距离 Rdet"):
    fig, ax = plt.subplots(figsize=(7.2, 5.0), constrained_layout=True)
    vmax = np.nanmax(Z)
    im = ax.pcolormesh(mor_grid, alpha_grid, Z.T, shading="nearest",
                       cmap="viridis", vmin=0, vmax=vmax)
    cs = ax.contour(mor_grid, alpha_grid, Z.T, levels=list(levels),
                    colors="w", linewidths=1.8)
    ax.clabel(cs, fmt="%.1f km", fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("能见度 MOR (km，对数轴)")
    ax.set_ylabel("Ångström 指数 α")
    ax.set_title(f"{band}：{task_label}相图（w=1.5 cm, Cn²=1e-14, ΔT=10 K）")
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label(f"{task_label} (km)")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_critical(path, df, R_target=8.0):
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), constrained_layout=True)
    d = df[df.kind == "MOR_vs_alpha"]
    axes[0].plot(d.x, d.y, "o-", color="#C44E52")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("α")
    axes[0].set_ylabel("临界 MOR (km)")
    axes[0].set_title(f"(a) Rdet={R_target:.0f} km 的临界能见度 MOR*(α)")
    axes[0].grid(alpha=0.3)

    d = df[df.kind == "Cn2_vs_MOR"]
    axes[1].plot(d.x, d.y, "s-", color="#4C72B0")
    axes[1].set_xscale("log")
    axes[1].set_yscale("log")
    axes[1].set_xlabel("MOR (km)")
    axes[1].set_ylabel("临界 Cn² (m^-2/3)")
    axes[1].set_title("(b) 湍流容限 Cn²*(MOR)")
    axes[1].grid(alpha=0.3)

    d = df[df.kind == "w_vs_MOR"]
    axes[2].plot(d.x, d.y, "^-", color="#55A868")
    axes[2].set_xscale("log")
    axes[2].set_xlabel("MOR (km)")
    axes[2].set_ylabel("临界可降水量 w (cm)")
    axes[2].set_title("(c) 水汽容限 w*(MOR)")
    axes[2].grid(alpha=0.3)
    fig.suptitle("图 3  等性能边界（LWIR，探测任务 Rdet=8 km）", fontsize=11)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_pd_curves(path, sensor, target):
    fig, ax = plt.subplots(figsize=(7.4, 4.8), constrained_layout=True)
    cases = [
        ("基准 A0 (LWIR)", m.Atmo(23, 1.3, 1.5, 1e-14), "LWIR", "-"),
        ("中等霾 B3 (LWIR)", m.Atmo(5, 1.3, 1.5, 1e-14), "LWIR", "-"),
        ("低对比 B16 (LWIR)", m.Atmo(23, 1.3, 1.5, 1e-16), "LWIR", "--"),
        ("强湍流 C5 (LWIR)", m.Atmo(23, 1.3, 1.5, 1e-13), "LWIR", "-"),
        ("沙尘 C3 (MWIR)", m.Atmo(4, 0.3, 1.0, 1e-14), "MWIR", "-"),
        ("浓雾 C1 (LWIR)", m.Atmo(0.8, 0.0, 3.0, 1e-13), "LWIR", ":"),
    ]
    for name, atmo, band, ls in cases:
        t = target if name.find("低对比") < 0 else m.Target(target.size, 3.0, target.area)
        cur = m.pd_curve(atmo, band, sensor, t, R_grid=np.linspace(0.2, 12, 100),
                         n50=sensor.n50_detect)
        ax.plot([c["R_km"] for c in cur], [c["pd"] for c in cur],
                ls, lw=1.7, label=name)
    ax.axhline(0.5, color="gray", lw=0.8, ls="--")
    ax.set_xlabel("作用距离 R (km)")
    ax.set_ylabel("探测概率 P_d")
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title("图 4  探测概率随距离的变化（简化模型，N50=2）")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_sobol(path, sobol_lwir, sobol_mwir):
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.0), constrained_layout=True)
    names = ex.PARAM_NAMES
    x = np.arange(len(names))
    for ax, dat, band in zip(axes, [sobol_lwir, sobol_mwir], ["LWIR", "MWIR"]):
        ax.bar(x - 0.2, dat["S1"], width=0.4, label="一阶 S1", color="#4C72B0")
        ax.bar(x + 0.2, dat["ST"], width=0.4, label="总指数 ST", color="#DD8452")
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Sobol 指数（Rdet 的方差贡献）")
        ax.set_title(f"{band}")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("图 5  探测距离 Rdet 的全局敏感性（GP 代理模型，N=1024）", fontsize=11)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_turbulence(path, sensor, target):
    fig, ax = plt.subplots(figsize=(7.0, 4.6), constrained_layout=True)
    cn2 = np.geomspace(1e-16, 1e-12, 25)
    for mor in [23.0, 10.0, 5.0, 2.0]:
        ys = [m.range_for_pd(m.Atmo(mor, 1.3, 1.5, c), "LWIR", sensor, target,
                             0.5, n50=sensor.n50_detect, Rmax=80)
              for c in cn2]
        ax.plot(cn2, ys, "o-", ms=3, lw=1.4, label=f"MOR={mor:g} km")
    ax.set_xscale("log")
    ax.set_xlabel("湍流强度 Cn² (m^-2/3，对数轴)")
    ax.set_ylabel("探测距离 Rdet (km)")
    ax.set_ylim(0, None)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title("图 6  湍流对探测距离的影响（LWIR，w=1.5 cm，ΔT=10 K）")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_pd_heatmap(path, sensor, target, mor_grid, R_grid, Z, band="LWIR"):
    fig, ax = plt.subplots(figsize=(7.2, 5.0), constrained_layout=True)
    im = ax.pcolormesh(mor_grid, R_grid, Z.T, shading="nearest",
                       cmap="magma", vmin=0, vmax=1)
    cs = ax.contour(mor_grid, R_grid, Z.T, levels=[0.5], colors="w", linewidths=1.8)
    ax.clabel(cs, fmt="Pd=0.5", fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("能见度 MOR (km，对数轴)")
    ax.set_ylabel("作用距离 R (km)")
    ax.set_title(f"{band}：探测概率相图（α=1.3, w=1.5, Cn²=1e-14, ΔT=10 K，N50=2）")
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("探测概率 P_d")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_weather_matrix(path, panels, band, metric_label, levels, vmax, fixed_text):
    """2x3 天气因子两两组合热力图。panels: dict(xname,yname,X,Y,Z,xlog,ylog)。"""
    fig, axes = plt.subplots(2, 3, figsize=(15.5, 8.6), constrained_layout=True)
    for ax, p in zip(axes.ravel(), panels):
        X, Y, Z = p["X"], p["Y"], p["Z"]
        im = ax.pcolormesh(X, Y, Z.T, shading="nearest", cmap="viridis",
                           vmin=0, vmax=vmax)
        cs = ax.contour(X, Y, Z.T, levels=list(levels), colors="w", linewidths=1.1)
        ax.clabel(cs, fmt="%.1f", fontsize=8)
        if p["xlog"]:
            ax.set_xscale("log")
        if p["ylog"]:
            ax.set_yscale("log")
        ax.set_xlabel(f"{p['xname']} ({p['xunit']})")
        ax.set_ylabel(f"{p['yname']} ({p['yunit']})")
        ax.set_title(f"{p['xname']} × {p['yname']}", fontsize=10)
    cb = fig.colorbar(im, ax=axes, shrink=0.9, pad=0.02)
    cb.set_label(metric_label)
    fig.suptitle(f"{band}：天气因子两两组合（{fixed_text}）", fontsize=12)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def fig_band_compare(path, X, Y, Z_lwir, Z_mwir, levels, metric_label, fixed_text):
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.6), constrained_layout=True)
    vmax = max(np.nanmax(Z_lwir), np.nanmax(Z_mwir))
    for ax, Z, title in zip(axes[:2], [Z_lwir, Z_mwir], ["LWIR", "MWIR"]):
        im = ax.pcolormesh(X, Y, Z.T, shading="nearest", cmap="viridis",
                           vmin=0, vmax=vmax)
        cs = ax.contour(X, Y, Z.T, levels=list(levels), colors="w", linewidths=1.2)
        ax.clabel(cs, fmt="%.1f", fontsize=8)
        ax.set_xscale("log")
        ax.set_xlabel("MOR (km)")
        ax.set_ylabel("Ångström α")
        ax.set_title(title)
    cb1 = fig.colorbar(im, ax=axes[:2], shrink=0.9, pad=0.02)
    cb1.set_label(metric_label)

    D = Z_mwir - Z_lwir
    m = max(abs(np.nanmin(D)), abs(np.nanmax(D))) + 1e-9
    im2 = axes[2].pcolormesh(X, Y, D.T, shading="nearest", cmap="RdBu_r",
                             vmin=-m, vmax=m)
    axes[2].set_xscale("log")
    axes[2].set_xlabel("MOR (km)")
    axes[2].set_ylabel("Ångström α")
    axes[2].set_title("MWIR − LWIR (km)")
    cb2 = fig.colorbar(im2, ax=axes[2], shrink=0.9, pad=0.02)
    cb2.set_label("差值 (km)")
    fig.suptitle(f"波段对比：{metric_label}（{fixed_text}）", fontsize=12)
    fig.savefig(path, dpi=150)
    plt.close(fig)

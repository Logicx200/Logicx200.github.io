# -*- coding: utf-8 -*-
"""
3-5 um 夜间地面：湍流对分辨率的影响（与视在温差图同一波段/场景）
A: Fried 相干直径 r0(Cn2, R)
B: 目标角尺寸 theta_t 下的可分辨周数 N_e(Cn2, theta_t)，R=2 km
简化模型（可行性研究）：水平均匀 Cn2，无外尺度/风/闪烁，D=0.2 m
"""
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LogNorm
from matplotlib.ticker import FixedLocator, NullFormatter, LogLocator

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "mathtext.fontset": "dejavusans",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# ---------------- 参数 ----------------
LAM = 4.0e-6          # m, 3-5 um 波段中心
D_AP = 0.20           # m, 假设口径（可改）
R_REF = 2.0           # km, 与视在温差图一致
THETA_REF = 1.0e-3    # rad, 1 mrad 参考目标

K = 2 * np.pi / LAM
THETA_DIFF = LAM / D_AP


def r0_of(cn2, r_km):
    """Fried parameter (m) for horizontal homogeneous path."""
    path_m = np.asarray(r_km) * 1000.0
    return (0.423 * K**2 * np.asarray(cn2) * path_m) ** (-3.0 / 5.0)


def theta_eff_of(cn2, r_km):
    r0 = r0_of(cn2, r_km)
    return np.hypot(LAM / r0, THETA_DIFF), r0


def n_cycles(cn2, theta_t, r_km=R_REF):
    te, _ = theta_eff_of(cn2, r_km)
    return np.asarray(theta_t) / te

# ---------------- 网格 ----------------
CN2_A = np.logspace(-16, -12, 121)
R_A = np.linspace(0.5, 10.0, 121)
X_A, Y_A = np.meshgrid(CN2_A, R_A)
R0_A = r0_of(X_A, Y_A) * 100.0  # cm

CN2_B = np.logspace(-16, -12, 121)
TH_B = np.logspace(np.log10(0.05), np.log10(10.0), 121)  # mrad
X_B, Y_B = np.meshgrid(CN2_B, TH_B)
N_B = n_cycles(X_B, Y_B * 1e-3)
R0_B = r0_of(X_B, R_REF) * 100.0

print("r0 range cm", float(R0_A.min()), float(R0_A.max()))
print("N range", float(N_B.min()), float(N_B.max()))

np.savez_compressed(
    os.path.join(HERE, "_turbulence_grid.npz"),
    cn2_a=CN2_A, r_a=R_A, r0_cm=R0_A,
    cn2_b=CN2_B, theta_mrad=TH_B, n_cycles=N_B, r0_b_cm=R0_B,
)

# ---------------- 画图 ----------------
fig = plt.figure(figsize=(13.4, 6.8), dpi=140)

# Panel A
axA = fig.add_axes([0.060, 0.255, 0.365, 0.600])
pcmA = axA.pcolormesh(X_A, Y_A, R0_A, norm=LogNorm(vmin=0.3, vmax=800),
                      cmap="viridis", shading="auto", rasterized=True)
axA.set_xscale("log")
axA.set_xlim(CN2_A[0], CN2_A[-1])
axA.set_ylim(R_A[0], R_A[-1])
axA.set_xlabel(r"湍流结构常数  $C_n^2$（m$^{-2/3}$，对数）", fontsize=10.5)
axA.set_ylabel("水平路径长度  R（km）", fontsize=10.5)
axA.set_title("A｜Fried 相干直径  $r_0$（cm，λ=4 μm）", fontsize=11.5, pad=8)
for x in (1e-15, 1e-14, 1e-13):
    axA.axvline(x, color="white", lw=0.8, ls=(0, (4, 3)), alpha=0.7)
for x, lab in ((1e-15, "弱"), (1e-14, "中"), (1e-13, "强")):
    axA.text(x, 9.55, lab, ha="center", va="top", fontsize=7.5, color="white",
             path_effects=[pe.withStroke(linewidth=1.8, foreground="#333333")])
axA.axhline(R_REF, color="#ffb347", lw=1.4, ls="--")
axA.text(1.3e-16, R_REF + 0.25, "视在温差图路径 R=2 km", color="#ffb347", fontsize=7.5)
levelsA = [1, 2, 5, 10, 20, 50, 100, 200, 500]
csa = axA.contour(X_A, Y_A, R0_A, levels=levelsA, colors="white", linewidths=0.75, alpha=0.8)
cla = axA.clabel(csa, fmt="%g", fontsize=6.5, colors="#222222", inline=True)
for t in cla:
    t.set_path_effects([pe.withStroke(linewidth=1.8, foreground="white")])
caxA = fig.add_axes([0.438, 0.305, 0.0115, 0.470])
cbA = fig.colorbar(pcmA, cax=caxA)
cbA.set_label(r"$r_0$（cm）", fontsize=9.5)
cbA.ax.tick_params(labelsize=8.5)

# Panel B
axB = fig.add_axes([0.545, 0.255, 0.365, 0.600])
pcmB = axB.pcolormesh(X_B, Y_B, N_B, norm=LogNorm(vmin=0.1, vmax=500),
                      cmap="magma", shading="auto", rasterized=True)
axB.set_xscale("log")
axB.set_yscale("log")
axB.set_xlim(CN2_B[0], CN2_B[-1])
axB.set_ylim(TH_B[0], TH_B[-1])
axB.set_xlabel(r"湍流结构常数  $C_n^2$（m$^{-2/3}$，对数）", fontsize=10.5)
axB.set_ylabel("目标角尺寸  θ$_t$（mrad，对数）", fontsize=10.5)
axB.set_title("B｜可分辨周数  $N_e$（R=2 km，D=0.2 m）", fontsize=11.5, pad=8)
levelsB = [0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
csb = axB.contour(X_B, Y_B, N_B, levels=levelsB, colors="white", linewidths=0.75, alpha=0.8)
clb = axB.clabel(csb, fmt="%g", fontsize=6.5, colors="#222222", inline=True)
for t in clb:
    t.set_path_effects([pe.withStroke(linewidth=1.8, foreground="white")])
axB.axhline(1.0, color="#ffb347", lw=1.2, ls="--")
axB.text(1.3e-16, 1.08, "参考目标 1 mrad", color="#ffb347", fontsize=7.5)
for x, lab in ((1e-15, "弱"), (1e-14, "中"), (1e-13, "强")):
    axB.text(x, 9.4, lab, ha="center", va="top", fontsize=7.5, color="white",
             path_effects=[pe.withStroke(linewidth=1.8, foreground="#333333")])
caxB = fig.add_axes([0.923, 0.305, 0.0115, 0.470])
cbB = fig.colorbar(pcmB, cax=caxB)
cbB.set_label(r"可分辨周数  $N_e$", fontsize=9.5)
cbB.ax.tick_params(labelsize=8.5)

# 标题与脚注
fig.text(0.5, 0.958, "3–5 μm 夜间地面：湍流对分辨率的影响（简化模型 · 可行性研究）",
         ha="center", fontsize=15.5, fontweight="bold")
fig.text(0.5, 0.915,
         r"λ=4 μm ｜ 水平均匀 $C_n^2$ ｜ 与视在温差图同一场景（夜间地面，R=2 km）｜ 口径 D=0.2 m（假设）｜ 参考目标 1 mrad ≈ 2 m @ 2 km",
         ha="center", fontsize=8.8, color="#444444")

notes = [
    r"注：① 湍流与气溶胶/水汽独立，故坐标轴用 $C_n^2$ 与路径长度/目标角尺寸；$r_0=[0.423k^2\!\!\int C_n^2\,dh]^{-3/5}$，水平均匀路径取 $\int C_n^2 dh=C_n^2 R$，λ=4 μm。",
    r"② 有效角分辨率 $\theta_{eff}=\sqrt{(\lambda/r_0)^2+(\lambda/D)^2}$，可分辨周数 $N_e=\theta_t/\theta_{eff}$（不含目标对比度/SNR）。",
    "③ 简化：无外尺度、风、闪烁、斜程与垂直廓线；D=0.2 m 为假设口径；C_n² 弱/中/强约 1e-15/1e-14/1e-13 m^-2/3。",
    "④ 结果仅作量级/趋势判断；正式版按实际 C_n² 廓线、口径、目标角尺寸与波段响应计算。",
]
fig.text(0.060, 0.135, "\n".join(notes), ha="left", va="top", fontsize=7.1,
         linespacing=1.55, color="#3d3d3d")

fig.savefig(os.path.join(HERE, "湍流分辨率热力图_3-5um_夜间.png"), dpi=300)
fig.savefig(os.path.join(HERE, "湍流分辨率热力图_3-5um_夜间.pdf"))
print("saved figure")

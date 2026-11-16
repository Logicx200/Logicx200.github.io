# -*- coding: utf-8 -*-
"""
3-5 um 夜间地面背景：视在温差 ΔT_app 的 (sigma_a, PWV) 参数扫描热力图
简化模型（可行性研究）：
  - 气体：HITRAN/HAPI 逐线吸收（H2O, CO2, O3, N2O, CO, CH4），283.15 K, 1.01325 atm
  - 气溶胶：Angstrom 消光，sigma_a(550) 为横轴，alpha 固定，水平均匀路径
  - 路径：水平 2 km，均匀温度 283.15 K；热发射 L_path = B(T)(1-tau)
  - 目标/背景：地面黑体（eps=1），T_t=288.15 K (15C), T_bg=283.15 K (10C)
  - 波段：3-5 um 平顶响应；不做散射、水汽连续吸收、垂直廓线
"""
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.ticker import FixedLocator, NullFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "mathtext.fontset": "dejavusans",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# ---------------- 常数与场景假设 ----------------
h = 6.62607015e-34
c = 2.99792458e8
kB = 1.380649e-23
NA = 6.02214076e23
T_AIR = 283.15          # 夜间近地面气温 = 背景温度 10 C
T_BG = 283.15           # 背景 10 C
T_TGT = 288.15          # 目标 15 C
P_SURF = 101325.0       # Pa
R_KM = 2.0              # 水平路径长度 km
L_CM = R_KM * 1e5       # cm
ALPHA = 1.2             # 中纬度混合型气溶胶 Angstrom 指数
H2O_SCALE_HT = 2000.0   # m，用于 PWV -> 地面水汽密度
M_H2O = 0.018015        # kg/mol

MIXING = {"CO2": 420e-6, "O3": 4.0e-8, "N2O": 3.32e-7, "CO": 1.5e-7, "CH4": 1.9e-6}

NU_MIN, NU_MAX = 2000.0, 3400.0
NU_STEP = 0.05
BAND_MIN, BAND_MAX = 2000.0, 10000.0 / 3.0  # 5 um -> 3 um

# ---------------- 读入截面 ----------------
d = np.load(os.path.join(HERE, "_xsect_3_5um.npz"))
NU = d["nu"]
BAND = (NU >= BAND_MIN) & (NU <= BAND_MAX)
NU_B = NU[BAND]
LAM_UM = 1e4 / NU_B
GAS_LIST = [n for n in ["H2O", "CO2", "CH4", "N2O", "CO", "O3"] if n in d.files]
print("gases included:", GAS_LIST)


def b_cm(nu_cm, T):
    """Planck spectral radiance, W m^-2 sr^-1 per cm^-1."""
    nu_m = np.asarray(nu_cm) * 100.0
    x = h * c * nu_m / (kB * T)
    return 2.0 * h * c**2 * nu_m**3 / np.expm1(x) * 100.0


def b_band(T):
    return float(np.sum(b_cm(NU_B, T)) * NU_STEP)


TGRID = np.linspace(120.0, 450.0, 1321)
BGRID = np.array([b_band(t) for t in TGRID])


def t_app(l_band):
    return np.interp(l_band, BGRID, TGRID)


def n_air_m3():
    return P_SURF / (kB * T_AIR)


def tau_gas(pwv_cm):
    """Gas optical depth on band grid for a horizontal path; PWV total column in cm."""
    rho_v = PWV_TO_RHO * pwv_cm          # kg/m3
    n_h2o = rho_v / M_H2O * NA           # molecules/m3
    tau = np.zeros_like(NU_B)
    for name, x in MIXING.items():
        if name not in GAS_LIST:
            continue
        n = x * n_air_m3()
        tau += d[name][BAND] * (n * 1e-6) * L_CM
    tau += d["H2O"][BAND] * (n_h2o * 1e-6) * L_CM
    return tau


# PWV_total -> 地面水汽密度：柱 = rho * H_scale；路径水平 2 km 与 H_scale 相同
PWV_TO_RHO = 10.0 / H2O_SCALE_HT  # kg/m3 per cm PWV: 1 cm = 10 kg/m2


def tau_aer(siga550):
    return siga550 * (LAM_UM / 0.55) ** (-ALPHA) * R_KM


# ---------------- 参数网格 ----------------
SIGMA = np.logspace(np.log10(0.02), np.log10(2.0), 81)
PWV = np.linspace(0.2, 1.8, 51)   # 10 C 地面饱和限制约 1.9 cm

DT = np.zeros((len(PWV), len(SIGMA)))
TAU_BAND = np.zeros_like(DT)
TAU_GAS_ONLY = np.zeros_like(DT)

for j, pwv in enumerate(PWV):
    tg = tau_gas(pwv)
    for i, siga in enumerate(SIGMA):
        tau_tot = tg + tau_aer(siga)
        tr = np.exp(-tau_tot)
        l_path = b_cm(NU_B, T_AIR) * (1.0 - tr)
        l_t = b_cm(NU_B, T_TGT) * tr + l_path
        l_b = b_cm(NU_B, T_BG) * tr + l_path
        lt = float(np.sum(l_t) * NU_STEP)
        lb = float(np.sum(l_b) * NU_STEP)
        DT[j, i] = t_app(lt) - t_app(lb)
        TAU_BAND[j, i] = float(np.sum(tr * b_cm(NU_B, T_BG)) / np.sum(b_cm(NU_B, T_BG)))
        TAU_GAS_ONLY[j, i] = float(np.sum(np.exp(-tg) * b_cm(NU_B, T_BG)) / np.sum(b_cm(NU_B, T_BG)))

print("DT range", float(np.nanmin(DT)), float(np.nanmax(DT)))
print("tau_band range", float(np.nanmin(TAU_BAND)), float(np.nanmax(TAU_BAND)))

np.savez_compressed(
    os.path.join(HERE, "_dtapp_grid.npz"),
    sigma=SIGMA, pwv=PWV, dt=DT, tau_band=TAU_BAND, tau_gas=TAU_GAS_ONLY,
)

# ---------------- 画图 ----------------
fig = plt.figure(figsize=(11.8, 8.8), dpi=140)
ax = fig.add_axes([0.085, 0.215, 0.795, 0.625])
X, Y = np.meshgrid(SIGMA, PWV)
vmin = float(np.floor(np.nanmin(DT) * 10) / 10)
vmax = float(np.ceil(np.nanmax(DT) * 10) / 10)
pcm = ax.pcolormesh(X, Y, DT, cmap="YlOrRd", vmin=vmin, vmax=vmax,
                    shading="auto", rasterized=True)
ax.set_xscale("log")
ax.set_xlim(SIGMA[0], SIGMA[-1])
ax.set_ylim(PWV[0], PWV[-1])

# 等值线
levels = np.arange(vmin + 0.25, vmax, 0.25)
cs = ax.contour(X, Y, DT, levels=levels, colors="white", linewidths=0.8, alpha=0.85)
cl = ax.clabel(cs, fmt="%.1f", fontsize=7, colors="#333333", inline=True)
for t in cl:
    t.set_path_effects([pe.withStroke(linewidth=2.0, foreground="white")])

ax.set_xlabel(r"550 nm 气溶胶消光系数  $\sigma_a(550)$（km$^{-1}$，对数坐标）", fontsize=11, labelpad=9)
ax.set_ylabel("可降水量  PWV（cm）", fontsize=11, labelpad=8)
ax.xaxis.set_major_locator(FixedLocator([0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]))
ax.set_xticklabels(["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"], fontsize=10)
ax.xaxis.set_minor_formatter(NullFormatter())
ax.tick_params(axis="both", labelsize=10)

cax = fig.add_axes([0.905, 0.27, 0.018, 0.47])
cb = fig.colorbar(pcm, cax=cax)
cb.set_label(r"视在温差  $\Delta T_{app}$（K）", fontsize=10.5, labelpad=10)
cb.ax.tick_params(labelsize=9)

fig.text(0.5, 0.960,
         "3–5 μm 夜间地面背景视在温差热力图（简化模型 · 可行性研究）",
         ha="center", fontsize=16, fontweight="bold")
fig.text(0.5, 0.921,
         r"水平路径 2 km ｜ 目标 15 °C / 背景 10 °C（地面黑体）｜ 中纬度夜间、$\alpha$=1.2 ｜ 颜色：入瞳视在温差 $\Delta T_{app}$",
         ha="center", fontsize=9.5, color="#444444")
fig.text(0.5, 0.893,
         "计算含路径辐亮度 L_path：L_app = L_int·τ + L_path；波段 3–5 μm 平顶响应",
         ha="center", fontsize=8.8, color="#666666")

notes = [
    "注：① 简化模型：气体吸收用 HITRAN 逐线（" + "/".join(GAS_LIST) + "，283 K、1 atm；N2O/O3/CO 暂缺，结果偏乐观）；气溶胶按 Ångström 定律（α=1.2）加到路径消光；忽略散射、水汽连续吸收和垂直廓线。",
    "② 目标/背景按地面黑体（ε=1）、同一路径计算，路径辐亮度对两者相同；ΔT_app 由波段辐亮度反演 Planck 得到，含路径辐射的压缩效应。",
    "③ 10 °C 地面饱和水汽限制 PWV 约 ≤1.9 cm，故纵轴取到 1.8 cm；更高 PWV 需更高地面温度（另算）。",
    "④ 结果仅用于量级/趋势的可行性判断，不作定量结论；正式版需完整 RT 模型（含散射、连续吸收、垂直廓线）与传感器参数。",
]
fig.text(0.085, 0.135, "\n".join(notes), ha="left", va="top", fontsize=7.2,
         linespacing=1.55, color="#3d3d3d")

fig.savefig(os.path.join(HERE, "视在温差热力图_3-5um_夜间.png"), dpi=300)
fig.savefig(os.path.join(HERE, "视在温差热力图_3-5um_夜间.pdf"))
print("saved figure")

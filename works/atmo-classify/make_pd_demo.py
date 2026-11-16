# -*- coding: utf-8 -*-
"""
P_d 演示（假设参数）：3-5 um 夜间地面背景
P_d = P_contrast × P_resolution
  - 对比度门限：ΔT_app/σ_noise，本场景 ΔT_app≈3-4 K >> NETD=25 mK，恒通过
  - 分辨率门限：Johnson 周数（用分辨单元数 N_e 的 logistic 近似）
假设传感器：D=0.2 m, f=0.4 m, pitch=15 um -> IFOV=37.5 urad, NETD=25 mK
任务门限（分辨单元）：探测 4, 识别 16, 辨认 26（≈2/8/13 周，1 周≈2 单元）
"""
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import Normalize
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

# ---------------- 假设 ----------------
LAM = 4.0e-6
D_AP = 0.20
F_LEN = 0.40
PITCH = 15e-6
IFOV = PITCH / F_LEN
NETD = 0.025          # K
DT_APP = 3.5          # K, 来自上一张图的典型值
N_REQ = {"探测": 4.0, "识别": 16.0, "辨认": 26.0}
SLOPE = 1.2           # logistic 斜率（分辨单元）

K = 2 * np.pi / LAM
THETA_DIFF = LAM / D_AP


def r0_of(cn2, r_km):
    return (0.423 * K**2 * np.asarray(cn2) * (np.asarray(r_km) * 1000.0)) ** (-3.0 / 5.0)


def n_elem(cn2, theta_t, r_km):
    r0 = r0_of(cn2, r_km)
    theta_sys = np.sqrt((LAM / r0) ** 2 + THETA_DIFF**2 + IFOV**2)
    return np.asarray(theta_t) / theta_sys


def p_resolution(ne, nreq):
    return 1.0 / (1.0 + np.exp(-(ne - nreq) / SLOPE))


def p_contrast():
    # 对比度门限（3 sigma）；本场景恒为 1，保留接口
    return 1.0


# ---------------- 图 A：P_d(检测) vs Cn2, theta_t ----------------
CN2 = np.logspace(-16, -12, 141)
TH = np.logspace(np.log10(0.05), np.log10(10.0), 141)
X, Y = np.meshgrid(CN2, TH)
NE = n_elem(X, Y * 1e-3, 2.0)
PD_A = p_resolution(NE, N_REQ["探测"]) * p_contrast()

# ---------------- 图 B：P_d vs 距离（三种任务） ----------------
R = np.linspace(1.0, 20.0, 200)
CN2_B = 1e-14
TARGET_M = 2.0
THETA_R = TARGET_M / (R * 1000.0)  # rad
NE_B = n_elem(CN2_B, THETA_R, R)
PD_B = {k: p_resolution(NE_B, nreq) * p_contrast() for k, nreq in N_REQ.items()}
R50 = {}
for _k, _v in PD_B.items():
    _idx = np.where(_v < 0.5)[0]
    R50[_k] = float(R[_idx[0]]) if len(_idx) else float("nan")
print("R50 km", R50)

print("Pd A range", float(PD_A.min()), float(PD_A.max()))
print("N_e at (1e-14, 1 mrad, 2 km):", float(n_elem(1e-14, 1e-3, 2.0)))

# ---------------- 画图 ----------------
fig = plt.figure(figsize=(13.2, 5.8), dpi=140)

# Panel A
axA = fig.add_axes([0.065, 0.235, 0.375, 0.610])
pcm = axA.pcolormesh(X, Y, PD_A, norm=Normalize(0, 1), cmap="RdYlGn",
                     shading="auto", rasterized=True)
axA.set_xscale("log")
axA.set_yscale("log")
axA.set_xlim(CN2[0], CN2[-1])
axA.set_ylim(TH[0], TH[-1])
axA.set_xlabel(r"湍流结构常数  $C_n^2$（m$^{-2/3}$，对数）", fontsize=10.3)
axA.set_ylabel("目标角尺寸  θ$_t$（mrad，对数）", fontsize=10.3)
axA.set_title("A｜探测概率 P$_d$（R=2 km，λ=4 μm，D=0.2 m）", fontsize=11.2, pad=8)
cs = axA.contour(X, Y, PD_A, levels=[0.1, 0.5, 0.9], colors="white", linewidths=0.8, alpha=0.85)
cl = axA.clabel(cs, fmt="%.1f", fontsize=7, colors="#222222", inline=True)
for t in cl:
    t.set_path_effects([pe.withStroke(linewidth=1.8, foreground="white")])
# 参考点
axA.plot(1e-14, 1.0, marker="o", ms=6, mfc="none", mec="#1f4e79", mew=1.6)
axA.annotate("参考：C$_n^2$=1e-14\nθ$_t$=1 mrad（2 m@2 km）",
             xy=(1e-14, 1.0), xytext=(4e-16, 0.12), fontsize=7,
             color="#1f4e79", arrowprops=dict(arrowstyle="-", color="#1f4e79", lw=0.8),
             bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="none", alpha=0.85))
caxA = fig.add_axes([0.452, 0.285, 0.0115, 0.51])
cbA = fig.colorbar(pcm, cax=caxA)
cbA.set_label("探测概率  P$_d$", fontsize=9.5)
cbA.ax.tick_params(labelsize=8.5)

# Panel B
axB = fig.add_axes([0.555, 0.235, 0.375, 0.610])
colors = {"探测": "#1f77b4", "识别": "#ff7f0e", "辨认": "#d62728"}
for k in ["探测", "识别", "辨认"]:
    axB.plot(R, PD_B[k], color=colors[k], lw=2.0, label=k)
axB.set_xlim(1, 20)
axB.set_ylim(0, 1.02)
axB.set_xlabel("目标距离  R（km）", fontsize=10.3)
axB.set_ylabel("任务概率  P", fontsize=10.3)
axB.set_title("B｜三种任务概率 vs 距离（目标 2 m，C$_n^2$=1e-14）", fontsize=11.2, pad=8)
axB.grid(True, color="#e2e2e2", lw=0.7)
axB.legend(fontsize=9, loc="upper right", frameon=False)
axB.text(9.8, 0.62,
         f"50% 距离：探测≈{R50['探测']:.1f} km\n识别≈{R50['识别']:.1f} km\n辨认≈{R50['辨认']:.1f} km",
         fontsize=7.4, color="#333333", va="top")

# 标题与注释
fig.text(0.5, 0.955, "探测概率 P_d 演示（假设典型 MWIR 传感器 · 3–5 μm 夜间地面）",
         ha="center", fontsize=15, fontweight="bold")
fig.text(0.5, 0.905,
         r"ΔT$_{app}$≈3.5 K（来自视在温差图）｜ NETD=25 mK ｜ D=0.2 m、IFOV=37.5 μrad ｜ 探测/识别/辨认门限≈2/8/13 周（4/16/26 分辨单元）",
         ha="center", fontsize=8.6, color="#444444")

notes = [
    "注：① P_d = P_contrast × P_resolution。本场景 ΔT_app/NETD≈140，对比度门限恒满足，因此 P_d 主要由分辨率（C_n²、目标角尺寸、距离）决定。",
    "② P_resolution 用 logistic 近似 Johnson 周数门限：P=1/[1+exp(−(N_e−N_req)/1.2)]；N_e=θ_t/θ_sys，θ_sys=√[(λ/r0)²+(λ/D)²+IFOV²]。",
    "③ 假设：目标/背景同路径、地面黑体、夜间、无杂波、无平台抖动；NETD、D、IFOV 为典型值，非实测；任务概率为 Johnson 型近似，非严格 ROC。",
    "④ 在 ($\\sigma_a$,PWV) 平面上，由于对比度充足，P_d 基本饱和为 1；要区分不同大气工况，需要看识别/辨认任务、更远距离或引入杂波。",
]
fig.text(0.065, 0.145, "\n".join(notes), ha="left", va="top", fontsize=7.2,
         linespacing=1.55, color="#3d3d3d")

fig.savefig(os.path.join(HERE, "Pd演示_3-5um_夜间.png"), dpi=300)
fig.savefig(os.path.join(HERE, "Pd演示_3-5um_夜间.pdf"))
print("saved figure")

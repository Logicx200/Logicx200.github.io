# -*- coding: utf-8 -*-
"""New V2.0 figures of the same types as the old report, drawn from software actual resources."""
import csv
import math
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

RES = r"F:\DeepSeek工作区\正式仿真\results"
os.makedirs(RES, exist_ok=True)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# ---------- constants from software actual resources ----------
WL = np.linspace(3.7, 4.8, 441) * 1e-6
H = 6.62607015e-34; C = 2.99792458e8; KB = 1.380649e-23

def planck_band(T):
    B = 2*H*C**2/WL**5 / np.expm1(H*C/(WL*KB*T))
    return np.trapezoid(B, WL)

T_GRID = np.linspace(150.0, 500.0, 3501)
B_GRID = np.array([planck_band(T) for T in T_GRID])
def t_app(L):
    return np.interp(L, B_GRID, T_GRID)

# ---------- fig 1: workflow ----------
fig, ax = plt.subplots(figsize=(13.2, 5.2), dpi=150)
ax.set_xlim(0, 13.2); ax.set_ylim(0, 5.2); ax.axis("off")
boxes = [
    (0.3, 3.4, 2.6, 1.2, "XGGDCOSSim2 实际资源\n默认想定 / 与那国岛\n6 个目标模型 / 默认气象"),
    (3.3, 3.4, 2.6, 1.2, "3.7–4.8 μm\n大气路径\nHITRAN + Ångström"),
    (6.3, 3.4, 2.6, 1.2, "目标/背景辐亮度\n与视在温差\nPlanck 反演"),
    (9.3, 3.4, 3.4, 1.2, "传感器模型\nIFOV / NETD / MTF\n分辨单元 Ne"),
    (6.3, 1.1, 2.6, 1.2, "任务概率\nJohnson 门限\n15,708 筛选点"),
    (9.3, 1.1, 3.4, 1.2, "V2.1 报告与数据表\n10 幅图 / CSV 结果\n可追溯"),
    (0.3, 1.1, 2.6, 1.2, "软件实际参数\n（非假设工况）\n可追溯"),
]
for (x, y, w, h, text), fc, ec in zip(boxes, ["#DCE6F1", "#E2EFDA", "#FCE4D6", "#DEEBF7", "#E2EFDA", "#FCE4D6", "#EDE7F6"],
                                      ["#1F4E79", "#548235", "#C55A11", "#2E75B6", "#548235", "#C55A11", "#7030A0"]):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
                                linewidth=1.0, edgecolor=ec, facecolor=fc))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=9.2, color="#333333")
arrows = [((2.9,4.0),(3.3,4.0)), ((5.9,4.0),(6.3,4.0)), ((8.9,4.0),(9.3,4.0)),
          ((7.6,3.4),(7.6,2.3)), ((10.9,2.3),(10.9,3.4)), ((2.9,1.7),(6.3,1.7)),
          ((5.9,1.7),(6.3,1.7)), ((8.9,1.7),(9.3,1.7)), ((0.3,1.7),(0.3,1.7))]
for (x1,y1),(x2,y2) in arrows:
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle="-|>",mutation_scale=12,
                                linewidth=1.0,color="#595959"))
ax.text(6.6, 4.92, "V2.1 仿真流程：仅采用软件内实际工况与目标参数", ha="center", va="center",
        fontsize=15, color="black", fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_workflow.png"), dpi=300)
plt.close(fig)

# ---------- fig 2: (sigma_a, PWV) parameter map with alpha color ----------
fig, ax = plt.subplots(figsize=(8.2, 5.2), dpi=150)
# actual software points
pts = [
    ("默认想定\n15 °C/50%/10 km\n干净大陆", 1.28, 0.352, 1.30, "#2c7fb8"),
    ("Q2 样本\n洛阳城市/10 °C/50%\n沙漠型", 0.94, 0.141, 0.30, "#e67e22"),
]
for label, pwv, sa, alpha, color in pts:
    ax.scatter([sa], [pwv], s=260, c=[alpha], cmap="RdYlBu_r", vmin=0.2, vmax=1.4,
               edgecolors="black", linewidths=0.8, zorder=3)
    ax.annotate(label, (sa, pwv), textcoords="offset points", xytext=(12, 8), fontsize=8.5, color=color)
    ax.annotate(f"α≈{alpha:.2f}", (sa, pwv), textcoords="offset points", xytext=(12, -20), fontsize=8, color="#333333")
ax.set_xscale("log")
ax.set_xlim(0.08, 0.55); ax.set_ylim(0.7, 1.6)
ax.set_xlabel("550 nm 气溶胶消光系数 σ$_a$(550)（km$^{-1}$，对数坐标）")
ax.set_ylabel("可降水量 PWV（cm）")
ax.set_title("软件内实际大气条件在 (σ$_a$, PWV) 参数平面上的位置（颜色=Ångström 指数 α）", fontsize=12, fontweight="bold")
ax.grid(alpha=.25)
sm = plt.cm.ScalarMappable(cmap="RdYlBu_r", norm=plt.Normalize(0.2, 1.4))
sm.set_array([])
cb = fig.colorbar(sm, ax=ax); cb.set_label("Ångström 指数 α")
ax.text(0.085, 1.53, "仅 2 个软件内实际大气条件；无软件外工况", fontsize=8.5, color="#666666")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_scenario_map.png"), dpi=300)
plt.close(fig)

# ---------- read actual results for tau/Lp / range ----------
rows = list(csv.DictReader(open(os.path.join(RES, "software_actual_case_results.csv"), encoding="utf-8-sig")))
f16 = sorted([r for r in rows if r["target"] == "F16战斗机" and r["state"] == "20 °C"], key=lambda r: float(r["ground_range_km"]))
ranges = np.array([float(r["ground_range_km"]) for r in f16])
tau = np.array([float(r["tau_band"]) for r in f16])
Lp = np.array([float(r["L_path"]) for r in f16])

# ---------- fig 3: dT_app heatmap over range x target temperature ----------
Tgrid = np.linspace(0.0, 60.0, 121)
B_t = np.array([planck_band(t + 273.15) for t in Tgrid])
B_bg = planck_band(293.15)
dT = np.zeros((len(Tgrid), len(ranges)))
for i, b in enumerate(B_t):
    Lt = 0.90 * b * tau + Lp
    Lb = 0.95 * B_bg * tau + Lp
    dT[i, :] = t_app(Lt) - t_app(Lb)
fig, ax = plt.subplots(figsize=(9.2, 5.0), dpi=150)
im = ax.imshow(dT, aspect="auto", origin="lower", extent=[ranges[0], ranges[-1], Tgrid[0], Tgrid[-1]],
               cmap="YlOrRd")
cs = ax.contour(ranges, Tgrid, dT, levels=[0, 5, 10, 15, 20, 25], colors="white", linewidths=0.8)
ax.clabel(cs, inline=True, fontsize=7, fmt="%.0f K")
ax.set_xlabel("地面距离（km）"); ax.set_ylabel("目标温度（°C）")
ax.set_title("F16 目标：视在温差随距离与目标温度变化（与那国岛背景 20 °C）")
cb = fig.colorbar(im, ax=ax); cb.set_label("ΔT_app（K）")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_dt_heatmap.png"), dpi=300)
plt.close(fig)

# ---------- fig 4: turbulence sensitivity heatmap (r0, Ne) ----------
CN2 = np.logspace(-16, -13, 61)  # 1e-16..1e-13
dim = 14.85
slant = np.sqrt(ranges**2 + (8000.0 - 500.0)**2 / 1e6)  # km
lam = 4.25e-6; D = 0.15; IFOV = np.deg2rad(3.75)/1024
r0 = np.zeros((len(CN2), len(ranges)))
ne = np.zeros_like(r0)
for i, cn in enumerate(CN2):
    r0v = (0.423*(2*np.pi/lam)**2*cn*(slant*1000.0))**(-3/5)
    th_eff = np.sqrt((lam/r0v)**2 + (lam/D)**2 + IFOV**2)
    r0[i, :] = r0v*100.0
    ne[i, :] = (dim/(slant*1000.0))/th_eff
fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.8), dpi=150)
for ax, data, title, lab, cmap in [(axes[0], r0, "Fried 相干直径 r0（cm）", "r0（cm）", "viridis"),
                                   (axes[1], ne, "分辨单元数 Ne", "Ne", "magma")]:
    im = ax.imshow(data, aspect="auto", origin="lower",
                   extent=[ranges[0], ranges[-1], np.log10(CN2[0]), np.log10(CN2[-1])], cmap=cmap)
    ax.set_xlabel("地面距离（km）"); ax.set_ylabel("log$_{10}$ Cn$^2$（m$^{-2/3}$）")
    ax.set_title(title)
    fig.colorbar(im, ax=ax).set_label(lab)
fig.suptitle("湍流敏感性（实际想定 Cn²=0，不参与主算例；本图仅给同类型敏感性分析）", fontsize=12, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_turbulence_heatmap.png"), dpi=300)
plt.close(fig)

# ---------- fig 5: Ne curves with old palette ----------
targets = ["F16战斗机", "F22战斗机", "尼米兹级航空母舰", "阿利伯克级驱逐舰", "悍马车", "爱国者导弹发射车"]
old_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
fig, ax = plt.subplots(figsize=(9.0, 4.8), dpi=150)
for tgt, col in zip(targets, old_colors):
    sub = sorted([r for r in rows if r["target"] == tgt and r["state"] == "40 °C"], key=lambda r: float(r["ground_range_km"]))
    ax.plot([float(r["ground_range_km"]) for r in sub], [float(r["Ne"]) for r in sub], lw=1.8, label=tgt, color=col)
for y, lab in [(4, "探测 4"), (16, "识别 16"), (26, "辨认 26")]:
    ax.axhline(y, ls="--", lw=0.9, color="#7f7f7f", alpha=.8)
    ax.text(20.15, y, lab, fontsize=7, va="center", color="#7f7f7f")
ax.set_yscale("log"); ax.set_xlabel("地面距离（km）"); ax.set_ylabel("分辨单元数 Ne（对数坐标）")
ax.set_title("6 个实际目标的分辨单元数随距离变化（40 °C 热状态）", fontsize=12, fontweight="bold")
ax.grid(alpha=.25, which="both"); ax.legend(fontsize=7, frameon=False, ncol=2)
fig.tight_layout()
fig.savefig(os.path.join(RES, "software_actual_ne.png"), dpi=300)
plt.close(fig)

print("extra figures saved")

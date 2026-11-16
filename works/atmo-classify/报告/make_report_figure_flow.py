# -*- coding: utf-8 -*-
"""Report workflow diagram: input layer -> physical chains -> path quantities -> test layer."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "mathtext.fontset": "dejavusans",
})

fig = plt.figure(figsize=(7.4, 4.4), dpi=300)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")


def box(x, y, w, h, title, body, fc, ec, fs=6.4):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.35,rounding_size=1.2",
                       linewidth=0.9, edgecolor=ec, facecolor=fc)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h - 3.4, title, ha="center", va="top", fontsize=fs + 0.6,
            fontweight="bold", color="#1a1a1a")
    ax.text(x + w / 2, y + h / 2 - 3.4, body, ha="center", va="center", fontsize=fs,
            color="#333333", linespacing=1.4)


def arrow(x1, y1, x2, y2, color="#666666"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=8, linewidth=0.9, color=color,
                                 shrinkA=1, shrinkB=1))


# ---- row 4 (bottom): test layer ----
box(3, 4, 94, 13, "检验层（任务级判定）",
    "$\\Delta T_{app}$ / SNR；$N_e$ / Johnson 周数；$P_d$ 与虚警率；任务等级（探测 / 识别 / 辨认）",
    "#fde9e9", "#b0413e", fs=6.6)
ax.text(50, 1.2, "数据与参考：MERRA-2 / AERONET / HITRAN / 传感器参数；工况范围与区域气候态见正文第 3 节",
        ha="center", va="center", fontsize=5.6, color="#666666")

# ---- row 3: path-integrated quantities ----
box(3, 25, 21, 14, "气溶胶/水汽透过率", "$\\tau_a(\\lambda)$, $\\tau_{H_2O}(\\lambda)$\n沿路径积分", "#e8f4ea", "#2e7d32")
box(27, 25, 21, 14, "路径辐亮度", "$L_{path}(\\lambda)$\n热发射 + 散射源项", "#fff3e0", "#b26a00")
box(51, 25, 21, 14, "湍流积分", "$r_0(\\lambda_{im})$\n$\\theta_{eff}$, $N_e$", "#eaf2fb", "#1f4e79")
box(75, 25, 22, 14, "汇合", "$L_{app}=L_{int}\\tau+L_{path}$\n$\\Delta T_{app}$, $N_e$", "#f3e8f7", "#7b3f8f")

# ---- row 2: chains ----
box(3, 46, 21, 14, "链 A｜气溶胶", "$\\sigma_a(\\lambda,h)$\nÅngström 外推", "#e8f4ea", "#2e7d32")
box(27, 46, 21, 14, "链 B｜水汽", "$k_{H_2O}(\\lambda;p,T)$\n逐层/逐线吸收", "#e8f4ea", "#2e7d32")
box(51, 46, 21, 14, "链 C｜源项", "$j(\\lambda,s)$\n温度廓线+散射", "#fff3e0", "#b26a00")
box(75, 46, 22, 14, "链 D｜湍流", "$C_n^2(h)$ 剖面积分\n系统 MTF", "#eaf2fb", "#1f4e79")

# ---- row 1: input layer ----
box(3, 67, 21, 14, "输入｜气溶胶", "$\\sigma_a(550)$, $\\alpha$, $H_a$", "#eef3f8", "#34568b")
box(27, 67, 21, 14, "输入｜水汽", "PWV + 温湿廓线", "#eef3f8", "#34568b")
box(51, 67, 21, 14, "输入｜几何/温度", "$h_s,h_t,\\theta,R$\n$T_{ground},T_{target},T_{bg}$", "#eef3f8", "#34568b")
box(75, 67, 22, 14, "输入｜湍流", "$A_{HV},v_{HV}$ 或\n$C_n^2(h_i)$ 剖面", "#eef3f8", "#34568b")

# arrows: input -> chains
for x in (13.5, 37.5, 61.5, 86):
    arrow(x, 67, x, 60)
# chains -> row3
for x in (13.5, 37.5, 61.5, 86):
    arrow(x, 46, x, 39)
# row3 -> row4 (selected)
for x in (13.5, 37.5, 61.5, 86):
    arrow(x, 25, x, 17)
# chain D also connects to resolution box via row3 right; already.

# labels for two channels
ax.text(50, 93, "红外目标探测大气参数化与成像效果检验流程", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color="#111111")
ax.text(50, 89, "三条大气链（A 气溶胶 / B 水汽 / C 源项）+ 湍流链 D；参数扫描 → 视在温差与可分辨周数 → 探测概率",
        ha="center", va="center", fontsize=6.8, color="#555555")

fig.savefig(os.path.join(HERE, "fig_workflow.png"), dpi=300, bbox_inches="tight",
            facecolor="white")
print("saved fig_workflow.png")

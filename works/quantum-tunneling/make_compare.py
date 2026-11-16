# -*- coding: utf-8 -*-
"""
量子隧穿 —— 动画场景对比图
==========================
读取 data/*_timeseries.npz 与重新计算的末态波函数, 生成:
  figures/anim_compare.png : 四个场景的概率分配演化 + 末态密度对比
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from tunneling_core import (gaussian_packet, grid_barrier, split_operator_evolve,
                            t_exact, t_wkb, spectrum_average_T)
from plot_style import setup_style, color

setup_style()
HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figures")
DATA = os.path.join(HERE, "data")

L, N = 400.0, 16384
X = np.linspace(-L / 2, L / 2, N, endpoint=False)
STRIDE = 8
XP = X[::STRIDE]
X0, SIGMA = -60.0, 8.0

SCEN = [
    ("barrier_a0.4", 2.0, 0.4, 1.8, 120.0),
    ("barrier_a1.0", 2.0, 1.0, 1.8, 120.0),
    ("barrier_a3.0", 2.0, 3.0, 1.5, 120.0),
    ("above_barrier", 1.0, 1.0, 1.8, 120.0),
]

fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.9))

for i, (name, V0, a, k0, Ttot) in enumerate(SCEN):
    d = np.load(os.path.join(DATA, f"{name}_timeseries.npz"))
    t = d["t"]
    T_ex = float(d["T_exact"])
    axes[0].plot(t, d["p_right"], color=color(i), lw=2.0,
                 label=f"$a$={a:g}, $V_0$={V0:g}: $T$={T_ex:.4f}")
    axes[0].axhline(T_ex, color=color(i), ls=":", lw=1.0, alpha=0.8)

    # 末态空间密度
    psi0 = gaussian_packet(X, X0, SIGMA, k0)
    V = grid_barrier(X, V0, a, edge_smooth=1.5)
    psi_f, snap, diag = split_operator_evolve(
        psi0, X, V, dt=0.0025, n_steps=int(Ttot / 0.0025), absorb_width=0)
    dens = np.abs(psi_f) ** 2
    axes[1].plot(XP, dens[::STRIDE], color=color(i), lw=2.0,
                 label=f"$a$={a:g}, $V_0$={V0:g}  透射={float(d['T_numeric']):.3f}")
    axes[1].plot(XP, V[::STRIDE] / V0 * (0.35 * dens[::STRIDE].max()),
                 color=color(i), lw=0.9, alpha=0.45)

axes[0].set_xlabel("时间 $t$")
axes[0].set_ylabel("势垒右侧概率 $P_R(t)$")
axes[0].set_title("(a) 不同参数下透射概率随时间的建立过程")
axes[0].legend(fontsize=8.5, loc="center right")
axes[0].set_xlim(0, 120)
axes[0].set_ylim(-0.02, 1.0)

axes[1].set_xlabel("位置 $x$")
axes[1].set_ylabel("末态概率密度 $|\\psi(x,t=120)|^2$")
axes[1].set_title("(b) 末态波包: 左峰=反射, 右峰=透射 (细线为势垒轮廓)")
axes[1].legend(fontsize=8.5)
axes[1].set_xlim(-200, 200)

fig.suptitle("图7  势垒参数对隧穿过程的影响 (时域仿真对比)", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.94))
p = os.path.join(FIGS, "anim_compare.png")
fig.savefig(p)
plt.close(fig)
print("->", p)

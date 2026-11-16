# -*- coding: utf-8 -*-
"""
量子隧穿 —— 参数扫描: 不同参数下的穿透(透射)概率
==================================================
产出 (figures/ 目录):
  fig1_T_vs_E_heights.png    : 固定垒宽, 改变垒高 -> T(E) 曲线族
  fig2_T_vs_E_widths.png     : 固定垒高, 改变垒宽 -> T(E) 曲线族
  fig3_heatmap.png           : T 关于 (垒高, 垒宽) / (垒宽, 能量) 的二维图谱
  fig4_exponential_decay.png : 隧穿区 ln T 与垒宽 a, sqrt(V0-E) 的线性关系
  fig5_wkb_accuracy.png      : 解析解 vs WKB vs 带前置因子 WKB 的精度对比
  fig6_sweep_summary.png     : 汇总六联图 (报告用主图)

所有曲线均用解析闭式解 t_exact 计算, 该式已由独立散射求解器
(线性方程组 + 界面连续性 + |t|^2+|r|^2=1) 验证到机器精度.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

from tunneling_core import t_exact, t_wkb, t_wkb_simple, transmission_matrix
from plot_style import setup_style, color, marker

HAVE_CJK = setup_style()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUT, exist_ok=True)
print("中文字体可用:", HAVE_CJK)

MASS = 1.0


# ----------------------------------------------------------------------
# 图 1: 不同势垒高度
# ----------------------------------------------------------------------
def fig1():
    a = 1.0
    E = np.linspace(1e-3, 6.0, 3000)
    heights = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    for i, V0 in enumerate(heights):
        T = t_exact(E, V0, a)
        axes[0].plot(E, T, color=color(i), lw=1.9, label=f"$V_0$ = {V0:g}")
        axes[0].axvline(V0, color=color(i), ls=":", lw=1.0, alpha=0.7)
        axes[1].semilogy(E, T, color=color(i), lw=1.9, label=f"$V_0$ = {V0:g}")
        axes[1].axvline(V0, color=color(i), ls=":", lw=1.0, alpha=0.7)
    for ax in axes:
        ax.set_xlabel("入射能量 $E$  (自然单位 $\\hbar=m=1$)")
        ax.legend(title="势垒高度", ncol=2)
    axes[0].set_ylabel("透射概率 $T$")
    axes[1].set_ylabel("透射概率 $T$  (对数轴)")
    axes[0].set_ylim(-0.02, 1.05)
    axes[1].set_ylim(1e-10, 2.0)
    axes[0].set_title(f"固定垒宽 $a$ = {a:g}: 垒高对隧穿概率的影响")
    axes[1].set_title("对数坐标: 隧穿区呈指数衰减, 越顶区出现共振振荡")
    axes[0].text(0.02, 0.06, "虚线: $E=V_0$ 分界\n左侧=量子隧穿区, 右侧=越顶区",
                 transform=axes[0].transAxes, fontsize=9,
                 bbox=dict(fc="white", ec="0.7", alpha=0.9))
    fig.suptitle("图1  不同势垒高度下的透射概率 $T(E)$", fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig1_T_vs_E_heights.png")
    fig.savefig(p); plt.close(fig)
    return p


# ----------------------------------------------------------------------
# 图 2: 不同势垒宽度
# ----------------------------------------------------------------------
def fig2():
    V0 = 2.0
    E = np.linspace(1e-3, 4.0, 3000)
    widths = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    for i, a in enumerate(widths):
        T = t_exact(E, V0, a)
        axes[0].plot(E, T, color=color(i), lw=1.9, label=f"$a$ = {a:g}")
        axes[1].semilogy(E, T, color=color(i), lw=1.9, label=f"$a$ = {a:g}")
    axes[0].axvline(V0, color="k", ls="--", lw=1.0)
    axes[1].axvline(V0, color="k", ls="--", lw=1.0)
    for ax in axes:
        ax.set_xlabel("入射能量 $E$")
        ax.legend(title="势垒宽度", ncol=2)
    axes[0].set_ylabel("透射概率 $T$")
    axes[1].set_ylabel("透射概率 $T$  (对数轴)")
    axes[0].set_ylim(-0.02, 1.05)
    axes[1].set_ylim(1e-10, 2.0)
    axes[0].set_title(f"固定垒高 $V_0$ = {V0:g}: 垒宽对隧穿概率的影响")
    axes[1].set_title("对数坐标: 垒宽每增加 $\\Delta a$, $\\ln T$ 线性下降")
    fig.suptitle("图2  不同势垒宽度下的透射概率 $T(E)$", fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig2_T_vs_E_widths.png")
    fig.savefig(p); plt.close(fig)
    return p


# ----------------------------------------------------------------------
# 图 3: 二维图谱 (垒高-能量, 垒宽-能量)
# ----------------------------------------------------------------------
def fig3():
    E = np.linspace(0.02, 5.0, 420)
    Vg = np.linspace(0.05, 6.0, 420)
    EV, VV = np.meshgrid(E, Vg)
    T1 = t_exact(EV.ravel(), VV.ravel(), 1.0).reshape(EV.shape)

    ag = np.linspace(0.05, 4.0, 420)
    EA, AA = np.meshgrid(E, ag)
    T2 = t_exact(EA.ravel(), 2.0, AA.ravel()).reshape(EA.shape)

    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.9))
    im0 = axes[0].pcolormesh(E, Vg, T1, shading="auto", cmap="viridis",
                             norm=LogNorm(vmin=1e-8, vmax=1.0))
    axes[0].plot(E, E, "w--", lw=1.4)
    axes[0].text(2.6, 1.1, "$E=V_0$\n(经典分界)", color="w", fontsize=9)
    axes[0].set_xlabel("入射能量 $E$")
    axes[0].set_ylabel("势垒高度 $V_0$")
    axes[0].set_title("$T(E,V_0)$, 垒宽 $a=1$")
    fig.colorbar(im0, ax=axes[0], label="透射概率 $T$")

    im1 = axes[1].pcolormesh(E, ag, T2, shading="auto", cmap="magma",
                             norm=LogNorm(vmin=1e-8, vmax=1.0))
    axes[1].axvline(2.0, color="w", ls="--", lw=1.4)
    axes[1].text(2.1, 3.2, "$E=V_0$", color="w", fontsize=9)
    axes[1].set_xlabel("入射能量 $E$")
    axes[1].set_ylabel("势垒宽度 $a$")
    axes[1].set_title("$T(E,a)$, 垒高 $V_0=2$")
    fig.colorbar(im1, ax=axes[1], label="透射概率 $T$")

    fig.suptitle("图3  透射概率的二维参数图谱 (对数色标)", fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig3_heatmap.png")
    fig.savefig(p); plt.close(fig)
    return p


# ----------------------------------------------------------------------
# 图 4: 指数律检验
# ----------------------------------------------------------------------
def fig4():
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 4.3))

    # (a) 固定 E, V0: ln T ~ -2 kappa a
    E, V0 = 0.5, 2.0
    kappa = np.sqrt(2.0 * MASS * (V0 - E))
    a = np.linspace(0.05, 6.0, 400)
    T = t_exact(E, V0, a)
    axes[0].semilogy(a, T, color=color(0), lw=2.2, label="解析解 $T(a)$")
    axes[0].semilogy(a, t_wkb(E, V0, a), color=color(1), lw=1.6, ls="--",
                     label="WKB  $e^{-2\\kappa a}$")
    axes[0].set_xlabel("势垒宽度 $a$")
    axes[0].set_ylabel("透射概率 $T$")
    axes[0].set_title(f"(a) 固定 $E$={E:g}, $V_0$={V0:g}\n$\\ln T$ 对 $a$ 为直线")
    axes[0].legend()

    # (b) ln T 与 a 的线性拟合
    lnT = np.log(T)
    fit = np.polyfit(a, lnT, 1)
    axes[1].plot(a, lnT, color=color(2), lw=2.0, label="解析解 $\\ln T$")
    axes[1].plot(a, np.polyval(fit, a), color="k", ls=":", lw=1.6,
                 label=f"线性拟合 斜率={fit[0]:.4f}")
    axes[1].axhline(np.log(1.0), color="0.6", lw=1.0)
    axes[1].set_xlabel("势垒宽度 $a$")
    axes[1].set_ylabel("$\\ln T$")
    axes[1].set_title(f"(b) 斜率 = {fit[0]:.4f},  理论 $-2\\kappa$ = {-2*kappa:.4f}")
    axes[1].legend()

    # (c) ln T 与 sqrt(V0-E)
    E2 = np.linspace(0.02, V0 - 0.02, 400)
    T2 = t_exact(E2, V0, 1.0)
    x = np.sqrt(2.0 * MASS * (V0 - E2))
    axes[2].plot(x, np.log(T2), color=color(3), lw=2.0, label="解析解 $\\ln T$")
    f2 = np.polyfit(x, np.log(T2), 1)
    axes[2].plot(x, np.polyval(f2, x), "k:", lw=1.6,
                 label=f"线性拟合 斜率={f2[0]:.4f}")
    axes[2].set_xlabel("$\\sqrt{2m(V_0-E)}$  (= $\\hbar\\kappa$)")
    axes[2].set_ylabel("$\\ln T$")
    axes[2].set_title(f"(c) 固定 $a$=1: 斜率 = {f2[0]:.4f}, 理论 $-2a$ = -2.0000")
    axes[2].legend()

    fig.suptitle("图4  隧穿概率的指数律: $T \\sim e^{-\\frac{2}{\\hbar}\\int\\sqrt{2m(V-E)}\\,dx}$",
                 fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig4_exponential_decay.png")
    fig.savefig(p); plt.close(fig)
    return p, fit[0], -2 * kappa, f2[0]


# ----------------------------------------------------------------------
# 图 5: 精确解 vs WKB 精度
# ----------------------------------------------------------------------
def fig5():
    V0, a = 5.0, 2.0
    E = np.linspace(0.05, 5.0, 2000)
    Te = t_exact(E, V0, a)
    Tw = t_wkb(E, V0, a)
    Ts = t_wkb_simple(E, V0, a)
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    axes[0].semilogy(E, Te, color=color(0), lw=2.2, label="解析精确解")
    axes[0].semilogy(E, Tw, color=color(1), lw=1.6, ls="--", label="WKB $e^{-2\\kappa a}$")
    axes[0].semilogy(E, Ts, color=color(2), lw=1.6, ls="-.", label="WKB + 前置因子")
    axes[0].axvline(V0, color="k", ls=":", lw=1.2)
    axes[0].set_xlabel("入射能量 $E$")
    axes[0].set_ylabel("透射概率 $T$")
    axes[0].set_title(f"$V_0$={V0:g}, $a$={a:g}: 三种计算方式")
    axes[0].legend()
    axes[1].plot(E, Ts / Te, color=color(2), lw=1.8, label="WKB+前置因子 / 精确")
    axes[1].plot(E, Tw / Te, color=color(1), lw=1.8, ls="--", label="WKB / 精确")
    axes[1].axhline(1.0, color="k", lw=1.0)
    axes[1].axvline(V0, color="k", ls=":", lw=1.2)
    axes[1].set_ylim(0.0, 2.2)
    axes[1].set_xlabel("入射能量 $E$")
    axes[1].set_ylabel("近似值 / 精确值")
    axes[1].set_title("WKB 的适用范围: 深隧穿 ($E \\ll V_0$) 最准,\n接近垒顶时失效")
    axes[1].legend()
    fig.suptitle("图5  WKB 近似的精度评估", fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig5_wkb_accuracy.png")
    fig.savefig(p); plt.close(fig)
    return p


# ----------------------------------------------------------------------
# 图 6: 汇总六联图
# ----------------------------------------------------------------------
def fig6():
    fig, axes = plt.subplots(2, 3, figsize=(15.6, 8.4))
    E = np.linspace(1e-3, 6.0, 3000)

    # (a) 垒高族
    for i, V0 in enumerate([0.5, 1.0, 2.0, 3.0, 5.0, 8.0]):
        axes[0, 0].semilogy(E, t_exact(E, V0, 1.0), color=color(i), lw=1.6,
                            label=f"$V_0$={V0:g}")
    axes[0, 0].set_title("(a) 不同垒高 $T(E)$, $a$=1")
    axes[0, 0].legend(ncol=2, fontsize=8)

    # (b) 垒宽族
    for i, a in enumerate([0.25, 0.5, 1.0, 2.0, 3.0, 5.0]):
        axes[0, 1].semilogy(E, t_exact(E, 2.0, a), color=color(i), lw=1.6,
                            label=f"$a$={a:g}")
    axes[0, 1].set_title("(b) 不同垒宽 $T(E)$, $V_0$=2")
    axes[0, 1].legend(ncol=2, fontsize=8)

    # (c) 垒宽指数律
    a = np.linspace(0.05, 6.0, 400)
    for i, E0 in enumerate([0.25, 0.5, 1.0, 1.5]):
        axes[0, 2].semilogy(a, t_exact(E0, 2.0, a), color=color(i), lw=1.8,
                            label=f"$E$={E0:g}")
    axes[0, 2].set_title("(c) $T(a)$ 指数衰减, $V_0$=2")
    axes[0, 2].set_xlabel("垒宽 $a$")
    axes[0, 2].legend(fontsize=8)

    # (d) 垒高扫描 (固定能量)
    Vg = np.linspace(0.02, 6.0, 700)
    for i, E0 in enumerate([0.25, 0.5, 1.0, 1.5, 2.5]):
        axes[1, 0].semilogy(Vg, t_exact(E0, Vg, 1.0), color=color(i), lw=1.8,
                            label=f"$E$={E0:g}")
    axes[1, 0].set_title("(d) $T(V_0)$ 扫描, $a$=1")
    axes[1, 0].set_xlabel("垒高 $V_0$")
    axes[1, 0].legend(fontsize=8)

    # (e) 质量依赖 (T 与粒子质量)
    mg = np.linspace(0.2, 4.0, 500)
    Eg = 0.5
    for i, aa in enumerate([0.5, 1.0, 2.0, 3.0]):
        axes[1, 1].semilogy(mg, t_exact(Eg, 2.0, aa, m=mg), color=color(i), lw=1.8,
                            label=f"$a$={aa:g}")
    axes[1, 1].set_title(f"(e) 粒子质量依赖 $T(m)$, $E$={Eg:g}, $V_0$=2")
    axes[1, 1].set_xlabel("粒子质量 $m$")
    axes[1, 1].legend(fontsize=8)

    # (f) 三种计算方法对比
    E2 = np.linspace(0.05, 5.0, 1500)
    axes[1, 2].semilogy(E2, t_exact(E2, 5.0, 2.0), color=color(0), lw=2.0, label="精确解")
    axes[1, 2].semilogy(E2, t_wkb(E2, 5.0, 2.0), color=color(1), lw=1.5, ls="--", label="WKB")
    axes[1, 2].semilogy(E2, t_wkb_simple(E2, 5.0, 2.0), color=color(2), lw=1.5, ls="-.",
                        label="WKB+前置因子")
    axes[1, 2].set_title("(f) 精确解 vs WKB, $V_0$=5, $a$=2")
    axes[1, 2].set_xlabel("入射能量 $E$")
    axes[1, 2].legend(fontsize=8)

    for ax in axes.ravel():
        ax.set_ylabel("透射概率 $T$")
        ax.set_ylim(1e-12, 3.0)
        if ax.get_xlabel() == "":
            ax.set_xlabel("入射能量 $E$")
    fig.suptitle("图6  量子隧穿穿透概率的参数扫描汇总 (自然单位 $\\hbar=m=1$)", fontsize=14)
    fig.tight_layout()
    p = os.path.join(OUT, "fig6_sweep_summary.png")
    fig.savefig(p); plt.close(fig)
    return p


# ----------------------------------------------------------------------
# 数值 vs 解析: 抽样点的时域模拟验证表
# ----------------------------------------------------------------------
def write_verification_table():
    """用独立散射求解器在抽样参数点上复核解析解, 输出表格文本."""
    rows = []
    rng = np.random.default_rng(20240607)
    for _ in range(24):
        V0 = float(rng.uniform(0.3, 6.0))
        a = float(rng.uniform(0.2, 3.0))
        E = float(rng.uniform(0.05, min(5.0, V0 + 2.0)))
        te = float(t_exact(E, V0, a))
        ts = transmission_matrix(E, [V0], [a])
        rows.append((V0, a, E, te, ts, abs(te - ts)))
    txt = ["解析闭式解 vs 独立散射求解器 随机抽样复核",
           f"{'V0':>8} {'a':>8} {'E':>8} {'T_exact':>16} {'T_solver':>16} {'|差|':>10}"]
    for V0, a, E, te, ts, d in rows:
        txt.append(f"{V0:8.4f} {a:8.4f} {E:8.4f} {te:16.8e} {ts:16.8e} {d:10.2e}")
    txt.append(f"最大绝对差 = {max(r[5] for r in rows):.3e}")
    p = os.path.join(OUT, "verification_table.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(txt))
    return p, max(r[5] for r in rows)


if __name__ == "__main__":
    print("生成图1 ..."); p1 = fig1()
    print("生成图2 ..."); p2 = fig2()
    print("生成图3 ..."); p3 = fig3()
    print("生成图4 ..."); p4, slope_fit, slope_th, slope2 = fig4()
    print("生成图5 ..."); p5 = fig5()
    print("生成图6 ..."); p6 = fig6()
    print("复核表格 ..."); p7, worst = write_verification_table()
    print()
    print(f"图4(b) lnT-a 拟合斜率 = {slope_fit:.5f}, 理论 -2*kappa = {slope_th:.5f}")
    print(f"图4(c) lnT-sqrt 拟合斜率 = {slope2:.5f}, 理论 -2a = -2.0")
    print(f"随机抽样复核最大绝对差 = {worst:.3e}")
    for p in [p1, p2, p3, p4, p5, p6, p7]:
        print("  ->", os.path.basename(p))

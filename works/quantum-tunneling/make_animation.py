# -*- coding: utf-8 -*-
"""
量子隧穿 —— 时域波包仿真动画
============================
用分步傅里叶法求解含时薛定谔方程, 逐帧记录 |psi(x,t)|^2 与动量谱,
生成波包入射 -> 与势垒作用 -> 部分隧穿 / 部分反射 的全过程动画。

每个场景产出:
  animations/tunneling_<name>.gif      : 时域动画
  figures/snap_<name>.png              : 关键帧静态图 (报告插图)
  data/<name>_timeseries.npz           : 时间序列数据 (可复算/绘图)

数值设定
--------
* 自然单位 hbar = m = 1, 方势垒 V(x) = V0 (|x| < a/2)
* 网格 N = 16384, L = 400, dx = 0.0244 (势垒宽 >= 41 格点)
* 势垒边缘用 1.5 dx 的 cos^2 斜坡平滑, 消除点取样阶跃势的量化误差
  (见 tunneling_core.grid_barrier 的说明)
* dt = 0.005, Strang 分裂 (二阶精度), 概率守恒到 1e-10 量级
* 不使用吸收边界: 演化时间受限于波包绕回 (L/|v_g|) 之前
"""

from __future__ import annotations

import os
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

from tunneling_core import (gaussian_packet, grid_barrier, split_operator_evolve,
                            t_exact, t_wkb, spectrum_average_T, phi_k, k_grid)
from plot_style import setup_style, color

HAVE_CJK = setup_style()
HERE = os.path.dirname(os.path.abspath(__file__))
ANIM = os.path.join(HERE, "animations")
FIGS = os.path.join(HERE, "figures")
DATA = os.path.join(HERE, "data")
for d in (ANIM, FIGS, DATA):
    os.makedirs(d, exist_ok=True)

# ----------------------------------------------------------------------
# 主网格
# ----------------------------------------------------------------------
L = 400.0
N = 16384
X = np.linspace(-L / 2, L / 2, N, endpoint=False)
DX = X[1] - X[0]
X0, SIGMA = -60.0, 8.0
EDGE_SMOOTH = 1.5

# 绘图用的空间抽样 (每 8 个格点取 1 个)
STRIDE = 8
XP = X[::STRIDE]
KGRID, DK = k_grid(X)
KPOS = KGRID > 0

# 场景定义: (名称, V0, a, k0, 演化总时长)
# 总时长受"波包绕回"限制: FFT 周期边界的对称像在 t_wrap 后重新进入势垒区.
# 对 (k0=1.8, L=400, 起始 x0=-60) 实测 t_wrap ≈ 130, 故统一取 120 留出裕量.
SCENARIOS = [
    ("barrier_a1.0", 2.0, 1.0, 1.8, 120.0),   # 中等隧穿, 部分透射
    ("barrier_a3.0", 2.0, 3.0, 1.5, 120.0),   # 厚垒, 强抑制
    ("barrier_a0.4", 2.0, 0.4, 1.8, 120.0),   # 薄垒, 大部分透射
    ("above_barrier", 1.0, 1.0, 1.8, 120.0),  # 越顶透射
]
DT = 0.0025
N_FRAMES = 240


def run_scenario(name, V0, a, k0, T_total, dt=DT, n_frames=N_FRAMES):
    """演化一个场景并返回动画所需数据."""
    n_steps = int(round(T_total / dt))
    record_at = sorted(set(np.linspace(0, n_steps, n_frames).astype(int).tolist()))
    psi0 = gaussian_packet(X, X0, SIGMA, k0)
    V = grid_barrier(X, V0, a, edge_smooth=EDGE_SMOOTH)
    E0 = 0.5 * k0 ** 2

    t0 = time.time()
    psi_f, snap, diag = split_operator_evolve(
        psi0, X, V, dt=dt, n_steps=n_steps, absorb_width=0,
        record_at=set(record_at), sample_at=record_at,
        keep_k=True, barrier_span=(-max(30.0, 3 * a), max(30.0, 3 * a)))
    elapsed = time.time() - t0

    psi_hist = np.array(snap["psi"])                    # (n_frames, N)
    t_hist = np.array(snap["t"])
    dens_hist = np.abs(psi_hist) ** 2
    dens_plot = dens_hist[:, ::STRIDE]
    k_hist = np.array(snap["k_dist"]) if len(snap["k_dist"]) else None
    # 动量谱密度 (归一化到积分 = 1)
    def kdens(i):
        raw = np.abs(phi_k(psi_hist[i], X)) ** 2
        return np.fft.fftshift(raw)

    stats = dict(
        V0=V0, a=a, k0=k0, E0=E0, dt=dt, T_total=T_total, L=L, N=N, dx=DX,
        sigma=SIGMA, x0=X0, edge_smooth=EDGE_SMOOTH,
        t=t_hist,
        p_left=np.array(diag["p_left"]),
        p_mid=np.array(diag["p_mid"]),
        p_right=np.array(diag["p_right"]),
        norm=np.array(diag["norm"]),
        T_exact=float(t_exact(E0, V0, a)),
        T_wkb=float(t_wkb(E0, V0, a)),
        T_spectral=float(spectrum_average_T(psi0, X, V0, a)),
        runtime=elapsed,
    )
    # 数值透射率: 取"波包已完全离开势垒区"的最长连续窗口内的中位数
    # (该窗口必须排除 t=0 附近垒内概率尚小的时刻, 也要排除波包绕回之后的时刻)
    pl = stats["p_left"]
    pr = stats["p_right"]
    pm = stats["p_mid"]
    settled = pm < 1e-6
    best_a = best_b = 0
    a0 = None
    for i, s in enumerate(list(settled) + [False]):
        if s and a0 is None:
            a0 = i
        elif not s and a0 is not None:
            if i - a0 > best_b - best_a:
                best_a, best_b = a0, i
            a0 = None
    if best_b - best_a >= 2:
        ratio = pr[best_a:best_b] / np.maximum(pl[best_a:best_b] + pr[best_a:best_b], 1e-300)
        stats["T_numeric"] = float(np.median(ratio))
        stats["T_numeric_std"] = float(np.std(ratio))
        stats["t_settle"] = float(t_hist[best_a])
        stats["t_settle_end"] = float(t_hist[best_b - 1])
    else:
        stats["T_numeric"] = float(pr[-1] / (pl[-1] + pr[-1]))
        stats["T_numeric_std"] = 0.0
        stats["t_settle"] = 0.0
        stats["t_settle_end"] = float(t_hist[-1])
    # 透射/反射波包动量谱 (末帧)
    stats["k"] = snap["k"]
    stats["k_initial"] = kdens(0)
    stats["k_final"] = kdens(-1)
    stats["k_mid"] = kdens(len(t_hist) // 3)
    return dens_plot, t_hist, psi_hist, stats, V


def make_animation(name, dens_plot, t_hist, psi_hist, stats, V, fps=22):
    """生成四联动画: 概率密度 + 对数密度 + 动量谱 + 概率随时间演化."""
    V0, a, k0 = stats["V0"], stats["a"], stats["k0"]
    E0 = stats["E0"]
    ymax = max(1.05 * dens_plot.max(), 0.05)
    V_plot = V[::STRIDE]
    k = stats["k"]
    thr = max(1e-12, ymax * 1e-7)

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.0))
    ax1, ax2, ax3, ax4 = axes.ravel()

    base = np.exp(-(XP - X0) ** 2 / (2 * SIGMA ** 2)) * (2 * np.pi * SIGMA ** 2) ** -0.5
    ax1.plot(XP, base, color="0.65", lw=1.2, ls="--", label="$t=0$ 初始波包")
    ax1.plot(XP, V_plot / max(V0, 1e-9) * ymax * 0.85, color="0.45", lw=1.8,
             label=f"势垒 $V_0$={V0:g}, $a$={a:g}")
    line1, = ax1.plot(XP, dens_plot[0], color=color(0), lw=2.0,
                      label="$|\\psi(x,t)|^2$", zorder=5)
    poly1 = ax1.fill_between(XP, 0, dens_plot[0], color=color(0), alpha=0.18)
    ax1.set_xlim(XP[0], XP[-1])
    ax1.set_ylim(0, ymax * 1.12)
    ax1.set_xlabel("位置 $x$")
    ax1.set_ylabel("概率密度 $|\\psi|^2$")
    ax1.set_title("(a) 位置空间: 波包入射、部分隧穿、部分反射")
    ax1.legend(loc="upper left", fontsize=8.5)

    ax2.plot(XP, V_plot, color="0.45", lw=1.8, label=f"势垒 $V_0$={V0:g}")
    line2, = ax2.semilogy(XP, np.clip(dens_plot[0], thr, None), color=color(1),
                          lw=1.8, label="$|\\psi|^2$ (对数)")
    ax2.set_xlim(XP[0], XP[-1])
    ax2.set_ylim(thr, ymax * 1.6)
    ax2.set_xlabel("位置 $x$")
    ax2.set_ylabel("$|\\psi|^2$")
    ax2.set_title("(b) 对数坐标: 垒内指数衰减 (隧穿特征)")
    ax2.legend(loc="upper left", fontsize=8.5)

    kk = k
    sel = (kk > -2.5) & (kk < 6.5)
    kf = stats["k_final"][sel]
    k_mid = stats["k_mid"][sel]
    ax3.plot(kk[sel], stats["k_initial"][sel], color="0.55", lw=1.4, ls="--",
             label="$t=0$ 动量谱")
    line3, = ax3.plot(kk[sel], k_mid, color=color(2), lw=1.8, label="中途动量谱")
    ax3.plot(kk[sel], kf, color=color(3), lw=1.8, label="末态动量谱")
    ax3.axvline(0.0, color="k", lw=0.9)
    ax3.axvline(np.sqrt(2 * V0), color="0.4", ls=":", lw=1.2)
    kmax_ax = ax3.get_ylim()[1]
    ax3.text(np.sqrt(2 * V0), kmax_ax * 0.72, " $k=\\sqrt{2V_0}$",
             fontsize=8, color="0.3")
    ax3.set_xlabel("波数 $k$  ( $p=\\hbar k$ )")
    ax3.set_ylabel("动量谱 $|\\phi(k)|^2$")
    ax3.set_title("(c) 动量空间: $k<0$ 反射分量, $k>0$ 透射分量")
    ax3.legend(loc="upper left", fontsize=8.5)

    ax4.axhline(stats["T_exact"], color=color(0), ls="--", lw=1.3,
                label=f"解析 $T(E_0)$={stats['T_exact']:.4f}")
    ax4.axhline(stats["T_spectral"], color=color(1), ls=":", lw=1.3,
                label=f"谱平均 $\\langle T\\rangle$={stats['T_spectral']:.4f}")
    lref, = ax4.plot([], [], color=color(3), lw=2.0, label="反射概率 $P_L(t)$")
    ltr, = ax4.plot([], [], color=color(4), lw=2.0, label="透射概率 $P_R(t)$")
    lbar, = ax4.plot([], [], color="0.5", lw=1.6, label="垒内概率 $P_M(t)$")
    ax4.set_xlim(0, t_hist[-1] * 1.02)
    ax4.set_ylim(-0.03, 1.05)
    ax4.set_xlabel("时间 $t$")
    ax4.set_ylabel("概率")
    ax4.set_title("(d) 概率分配随时间的演化")
    ax4.legend(loc="center right", fontsize=8.5)

    fig.suptitle(
        f"量子隧穿时域仿真   $V_0$={V0:g}, $a$={a:g}, $E_0$={E0:.3f} "
        f"({'$E_0>V_0$ 越顶' if E0 > V0 else '$E_0<V_0$ 隧穿'})   "
        f"$\\hbar=m=1$,  dx={DX:.4f}, dt={stats['dt']:g}",
        fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.955))

    def update(i):
        d = dens_plot[i]
        line1.set_ydata(d)
        verts = np.column_stack([
            np.concatenate([[XP[0]], XP, [XP[-1]]]),
            np.concatenate([[0.0], d, [0.0]])])
        poly1.set_verts([verts])
        line2.set_ydata(np.clip(d, thr, None))
        line3.set_ydata(np.fft.fftshift(np.abs(phi_k(psi_hist[i], X)) ** 2)[sel])
        lref.set_data(t_hist[:i + 1], stats["p_left"][:i + 1])
        ltr.set_data(t_hist[:i + 1], stats["p_right"][:i + 1])
        lbar.set_data(t_hist[:i + 1], stats["p_mid"][:i + 1])
        ax1.set_title(f"(a) 位置空间: 波包入射、部分隧穿、部分反射   $t$ = {t_hist[i]:.0f}")
        return line1, line2, line3, lref, ltr, lbar, poly1

    ani = FuncAnimation(fig, update, frames=len(t_hist), interval=1000 / fps, blit=False)
    gif = os.path.join(ANIM, f"tunneling_{name}.gif")
    ani.save(gif, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return gif


def make_snapshots(name, dens_plot, t_hist, stats, V):
    """关键帧静态图: 初始 / 作用中 / 末态."""
    V0, a, k0 = stats["V0"], stats["a"], stats["k0"]
    fracs = [0.0, 0.35, 1.0]
    idxs = [int(round(f * (len(t_hist) - 1))) for f in fracs]
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.3), sharey=True)
    ymax = 1.08 * dens_plot.max()
    V_plot = V[::STRIDE]
    for ax, i in zip(axes, idxs):
        ax.fill_between(XP, 0, dens_plot[i], color=color(0), alpha=0.28)
        ax.plot(XP, dens_plot[i], color=color(0), lw=1.8, label="$|\\psi(x,t)|^2$")
        ax.plot(XP, V_plot / max(V0, 1e-9) * ymax * 0.8, color="0.45", lw=1.8,
                label=f"势垒 $V_0$={V0:g}")
        ax.set_xlim(XP[0], XP[-1])
        ax.set_ylim(0, ymax)
        ax.set_xlabel("位置 $x$")
        ax.set_title(f"$t$ = {t_hist[i]:.0f}   "
                     f"左区概率 {stats['p_left'][i]:.3f}  |  "
                     f"垒内 {stats['p_mid'][i]:.2e}  |  "
                     f"右区概率 {stats['p_right'][i]:.3f}")
    axes[0].set_ylabel("概率密度 $|\\psi|^2$")
    axes[0].legend(loc="upper left", fontsize=8.5)
    fig.suptitle(f"图  时域波包演化关键帧  ($V_0$={V0:g}, $a$={a:g}, "
                 f"$E_0$={stats['E0']:.3f}, 数值透射率={stats['T_numeric']:.4f}, "
                 f"解析 $T(E_0)$={stats['T_exact']:.4f})", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    p = os.path.join(FIGS, f"snap_{name}.png")
    fig.savefig(p)
    plt.close(fig)
    return p


if __name__ == "__main__":
    print("中文字体可用:", HAVE_CJK)
    print(f"网格 N={N}, L={L}, dx={DX:.5f}, 记录步长 dt=0.005")
    summary = []
    for name, V0, a, k0, Ttot in SCENARIOS:
        print(f"\n=== 场景 {name}: V0={V0}, a={a}, k0={k0}, E0={0.5*k0**2:.3f}, "
              f"演化到 t={Ttot:g} ===")
        dens_plot, t_hist, psi_hist, stats, V = run_scenario(name, V0, a, k0, Ttot)
        stats["psi_hist"] = psi_hist
        print(f"  演化用时 {stats['runtime']:.1f}s, 帧数 {len(t_hist)}, "
              f"归一化 min={stats['norm'].min():.8f}")
        print(f"  垒内清空窗口 t ∈ [{stats['t_settle']:.0f}, {stats['t_settle_end']:.0f}]; "
              f"窗口内数值透射率={stats['T_numeric']:.6f} (波动 {stats['T_numeric_std']:.2e})")
        print(f"  解析 T(E0)={stats['T_exact']:.6f} | 谱平均 <T>={stats['T_spectral']:.6f} "
              f"| WKB={stats['T_wkb']:.4e}")
        np.savez_compressed(
            os.path.join(DATA, f"{name}_timeseries.npz"),
            t=t_hist, p_left=stats["p_left"], p_mid=stats["p_mid"],
            p_right=stats["p_right"], norm=stats["norm"], V0=V0, a=a, k0=k0,
            T_exact=stats["T_exact"], T_numeric=stats["T_numeric"],
            T_spectral=stats["T_spectral"], T_wkb=stats["T_wkb"],
            t_settle=stats["t_settle"], t_settle_end=stats["t_settle_end"],
            dt=DT, n_frames=len(t_hist),
            E0=stats["E0"], sigma=SIGMA, x0=X0, L=L, N=N)
        snap = make_snapshots(name, dens_plot, t_hist, stats, V)
        gif = make_animation(name, dens_plot, t_hist, psi_hist, stats, V)
        print(f"  -> {os.path.basename(gif)} ({os.path.getsize(gif)/1e6:.2f} MB)")
        print(f"  -> {os.path.basename(snap)}")
        summary.append((name, V0, a, k0, stats["T_numeric"], stats["T_exact"],
                        stats["T_spectral"]))
    print("\n" + "=" * 78)
    print(f"{'场景':>18} {'V0':>5} {'a':>5} {'E0':>7} {'数值T':>10} {'解析T(E0)':>11} {'谱平均':>10}")
    for r in summary:
        print(f"{r[0]:>18} {r[1]:5g} {r[2]:5g} {0.5*r[3]**2:7.3f} {r[4]:10.5f} "
              f"{r[5]:11.5f} {r[6]:10.5f}")

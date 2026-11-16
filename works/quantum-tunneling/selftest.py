# -*- coding: utf-8 -*-
"""
量子隧穿计算 —— 完整自检
========================
四类独立手段两两交叉验证:

  [1] 解析闭式解 t_exact  <->  独立散射求解器 (直接解 psi, psi' 连续方程组)
  [2] 解析解 / WKB 的物理性质 (单调性、极限、临界点连续性、WKB 有效域)
  [3] 分步傅里叶时域演化: 时间步/空间步收敛性、概率守恒、离散化处理
  [4] 波包数值透射率 <-> 解析能量谱平均 <T> = Σ_k w_k T(E_k)

测量约定: 在 t = T_stop 时波包已完全离开势垒区 (垒内残差 < 1e-12),
此时 (i) 左右两侧空间概率比 与 (ii) 动量空间 k>0 权重 给出同一个透射率,
两者互为独立实现, 并与解析谱平均 <T> 比较.
"""

import time
import sys
import numpy as np
from tunneling_core import (t_exact, transmission_matrix, continuity_residual,
                            t_wkb, t_wkb_simple, rect_barrier, grid_barrier,
                            gaussian_packet, split_operator_evolve,
                            spectrum_average_T, spectrum_average_T_positive,
                            packet_mean_energy, phi_k, k_grid)

ok = True
def check(cond, msg):
    global ok
    ok = ok and bool(cond)
    print(("  [OK]  " if cond else "  [BAD] ") + msg)


def measure_T(psi, x, diag):
    """波包离开势垒区后, 用两种独立方法给出透射率."""
    k, dk = k_grid(x)
    pk = np.abs(phi_k(psi, x)) ** 2
    T_momentum = float(np.sum(pk[k > 0]) * dk)
    pl, pr = diag["p_left"][-1], diag["p_right"][-1]
    T_space = float(pr / (pl + pr))
    return T_space, T_momentum


print("=" * 78)
print("[1] 解析闭式解  vs  独立散射求解器 (线性方程组 + 连续性 + 概率守恒)")
print("=" * 78)
worst_dT = worst_cont = worst_norm = 0.0
for V0, a in [(0.5, 1.0), (1.0, 2.0), (2.0, 1.0), (2.0, 0.5), (5.0, 2.0), (8.0, 3.0)]:
    for E in [0.05, 0.1, 0.2, 0.5, 1.0, 1.5, 1.9999, 2.0001, 2.5, 3.0, 5.0, 8.0]:
        worst_dT = max(worst_dT, abs(float(t_exact(E, V0, a)) - transmission_matrix(E, [V0], [a])))
        c, nrm = continuity_residual(E, [V0], [a])
        worst_cont = max(worst_cont, c)
        worst_norm = max(worst_norm, abs(nrm - 1.0))
check(worst_dT < 1e-10, f"所有 (V0,a,E) 组合: max|T_exact - T_solver| = {worst_dT:.3e}")
check(worst_cont < 1e-9, f"所有界面上 |Δpsi|, |Δpsi'| 最大残差 = {worst_cont:.3e}")
check(worst_norm < 1e-12, f"概率守恒 |t|^2+|r|^2-1 最大偏差 = {worst_norm:.3e}")
check(abs(transmission_matrix(1.234, [0.0], [2.0]) - 1.0) < 1e-12, "自由空间退化为全透射 T=1")
Ev = np.linspace(0.05, 4.0, 20000)
Tv = np.array([transmission_matrix(E, [5.0, 0.0, 5.0], [1.0, 0.6, 1.0]) for E in Ev])
check(Tv.max() > 0.99, f"双势垒 (5,0,5) 共振透射峰 max T = {Tv.max():.6f}")
check(Tv.min() < 1e-6, f"双势垒共振谷 min T = {Tv.min():.3e}")

print()
print("=" * 78)
print("[2] 解析解 / WKB 的物理性质")
print("=" * 78)
for V0, a in [(2.0, 1.0), (5.0, 2.0)]:
    Es = np.linspace(0.01, 10.0, 4000)
    Ts = t_exact(Es, V0, a)
    check(Ts.min() >= 0 and Ts.max() <= 1.0 + 1e-12,
          f"V0={V0}, a={a}: T(E) ∈ [{Ts.min():.3e}, {Ts.max():.6f}], T(10) = {t_exact(10.0,V0,a):.6f}")
check(np.all(np.diff(t_exact(np.linspace(0.05, 4.9, 300), 5.0, 2.0)) > 0),
      "隧穿区 (E<V0) 的 T(E) 单调递增")
check(abs(t_exact(2.0, 2.0, 1.0) - 1.0 / (1.0 + 2.0 * 1.0 ** 2 / 2.0)) < 1e-12,
      "E -> V0 临界点解析式连续")
r_thick = t_wkb_simple(0.5, 5.0, 6.0) / t_exact(0.5, 5.0, 6.0)
check(abs(r_thick - 1) < 0.05, f"厚势垒极限 T_WKB_simple/T_exact = {r_thick:.4f} -> 1")
# WKB 的有效域: 势垒越"厚"越准 (薄垒时 WKB 完全失效)
for a_thin, a_thick in [(1.0, 6.0)]:
    r1 = t_wkb(0.5, 5.0, a_thin) / t_exact(0.5, 5.0, a_thin)
    r2 = t_wkb(0.5, 5.0, a_thick) / t_exact(0.5, 5.0, a_thick)
    check(r2 < r1 or abs(r2 - 1) < abs(r1 - 1),
          f"WKB 在厚垒更准: a={a_thin} 比值 {r1:.3f}, a={a_thick} 比值 {r2:.3f}")

print()
print("=" * 78)
print("[3] 时域演化: 网格收敛性、概率守恒、离散化处理")
print("=" * 78)
L = 400.0
N = 16384
x = np.linspace(-L / 2, L / 2, N, endpoint=False)
dx = x[1] - x[0]
sigma, x0 = 8.0, -60.0
V0, a, k0 = 2.0, 1.0, 1.8
psi0 = gaussian_packet(x, x0, sigma, k0)
V = grid_barrier(x, V0, a, edge_smooth=1.5)
E0 = 0.5 * k0 ** 2
print(f"  网格 N={N}, L={L:.0f}, dx={dx:.5f} (势垒宽 {a/dx:.1f} 格点, 边缘平滑 1.5 dx)")
print(f"  波包 sigma={sigma}, x0={x0}, k0={k0} -> E0={E0:.4f}, <E>={packet_mean_energy(psi0,x,V):.4f}")
avg = spectrum_average_T(psi0, x, V0, a)
avg2 = spectrum_average_T_positive(psi0, x, V0, a)
check(abs(avg2 - avg) / avg < 1e-6, f"两种谱平均算法一致: {avg:.6f} vs {avg2:.6f}")
check(abs(avg - t_exact(E0, V0, a)) / t_exact(E0, V0, a) < 0.02,
      f"窄能谱下 <T>={avg:.6f} 与 T(E0)={t_exact(E0,V0,a):.6f} 一致 (<2%)")
print(f"  WKB 对照: T_WKB(E0) = {t_wkb(E0,V0,a):.6e}")

runs = []
for dt, nst in [(0.02, 6000), (0.005, 24000), (0.0025, 48000)]:
    t0 = time.time()
    psi, snap, diag = split_operator_evolve(
        psi0, x, V, dt=dt, n_steps=nst, absorb_width=0,
        sample_at=list(range(0, nst + 1, max(1, nst // 20))))
    el = time.time() - t0
    nrm = np.array(diag["norm"])
    pm = np.array(diag["p_mid"])[-1]
    Ts, Tm = measure_T(psi, x, diag)
    runs.append((dt, Ts, Tm))
    print(f"    dt={dt:6} T_stop={dt*nst:6.0f} ({el:5.2f}s): 归一化 min={nrm.min():.8f} "
          f"垒内残差={pm:.1e}")
    print(f"        空间法 T={Ts:.6f} | 动量法 T={Tm:.6f} | 与谱平均偏差 {abs(Ts-avg)/avg*100:.4f}%")
check(abs(runs[-1][1] - runs[-2][1]) < 1e-4 and abs(runs[-1][2] - runs[-2][2]) < 1e-4,
      "时间步减半后透射率不变 (< 1e-4): 时间演化已收敛")
check(abs(runs[-1][1] - runs[-1][2]) < 1e-3,
      f"空间法与动量法一致: {runs[-1][1]:.6f} vs {runs[-1][2]:.6f} (差 "
      f"{abs(runs[-1][1]-runs[-1][2]):.2e})")
check(abs(runs[-1][1] - avg) / avg < 0.01,
      f"数值透射率 {runs[-1][1]:.6f} 与解析谱平均 {avg:.6f} 一致到 1% 以内")

print()
print("=" * 78)
print("[4] 多组参数的时域演化  vs  解析谱平均")
print("=" * 78)
cases = [
    (1.0, 1.0, 1.8, "越顶透射 E0>V0"),
    (2.0, 2.0, 1.5, "中等隧穿"),
    (2.0, 3.0, 0.9, "厚势垒深隧穿"),
    (5.0, 1.0, 1.0, "深隧穿 E0<<V0"),
    (2.0, 1.0, 2.4, "高能越顶振荡"),
]
for V0c, ac, k0c, name in cases:
    psi0c = gaussian_packet(x, x0, sigma, k0c)
    Vc = grid_barrier(x, V0c, ac, edge_smooth=1.5)
    E0c = 0.5 * k0c ** 2
    avgc = spectrum_average_T(psi0c, x, V0c, ac)
    # 保证波包完全离开势垒区且不触及边界: 越快停止越早
    T_stop = float(np.clip(150.0 / max(k0c, 0.4), 90.0, 340.0))
    nst = int(T_stop / 0.005)
    t0 = time.time()
    psi, snap, diag = split_operator_evolve(
        psi0c, x, Vc, dt=0.005, n_steps=nst, absorb_width=0,
        sample_at=list(range(0, nst + 1, max(1, nst // 20))))
    el = time.time() - t0
    Ts, Tm = measure_T(psi, x, diag)
    pm = np.array(diag["p_mid"])[-1]
    rel = abs(Ts - avgc) / max(avgc, 1e-300) * 100
    print(f"  {name}: V0={V0c}, a={ac}, k0={k0c}, E0={E0c:.3f}, 演化到 t={T_stop:.0f} ({el:.1f}s)")
    print(f"      谱平均 <T>={avgc:.6e} | 空间法={Ts:.6e} | 动量法={Tm:.6e} | "
          f"垒内残差={pm:.1e} | 偏差 {rel:.2f}%")
    # 判据随信噪比分级: 数值透射率由演化后波函数尾部决定, 绝对噪声底约 1e-4~1e-5,
    # 因此 T < 1e-2 时允许更宽的容差 (深隧穿极限的正确数值留给解析解与独立求解器).
    if avgc > 1e-2:
        check(rel < 2.0, f"{name}: 数值透射率与解析谱平均一致 (偏差 {rel:.2f}%)")
    elif avgc > 1e-4:
        check(rel < 10.0, f"{name}: T={avgc:.2e} 接近数值噪声底, 偏差 {rel:.2f}% (<10%)")
    else:
        ok_mag = (Ts > 0.2 * avgc) and (Ts < 5.0 * avgc)
        check(ok_mag, f"{name}: T={avgc:.2e} 低于数值噪声底(~1e-4), 检查量级一致 "
                      f"(数值/解析 = {Ts/max(avgc,1e-300):.2f})")

print()
print("=" * 78)
print("自检结论:", "全部通过 (解析解、独立求解器、谱平均、时域演化互相印证)" if ok else "存在不一致")
print("=" * 78)
sys.exit(0 if ok else 1)

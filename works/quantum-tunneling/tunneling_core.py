# -*- coding: utf-8 -*-
"""
量子隧穿理论模型 —— 计算核心
==============================

自然单位制:  hbar = 1,  m = 1

本模块给出三类互相独立、可交叉验证的计算手段:

1. t_exact(E, V0, a)    : 方势垒的解析透射系数 (平面波散射, 闭式解)
2. t_wkb / t_wkb_simple : WKB 隧穿近似
3. split_operator_evolve: 分步傅里叶 (split-operator) 含时波包演化

交叉验证关系
------------
(a) t_exact  <-> transmission_matrix  : 解析闭式解 vs 通用转移矩阵
(b) 波包演化  <-> 谱平均             : 长时间演化后落在势垒右侧的概率,
                                        应等于入射波包能量谱对 T_exact(E)
                                        的加权平均  <T> = ∫ |phi(k)|^2 T(E_k) dE
(c) 能谱很窄 (sigma 大) 时 <T> -> T(E_0), 即回到准单能情形
"""

from __future__ import annotations

import numpy as np

HBAR = 1.0
MASS = 1.0

__all__ = [
    "HBAR", "MASS",
    "t_exact", "r_exact", "t_wkb", "t_wkb_simple", "transmission_matrix",
    "rect_barrier", "grid_barrier", "gaussian_packet", "packet_mean_energy",
    "split_operator_evolve", "spectrum_weights", "amplitude_weights",
    "spectrum_average_T", "spectrum_average_T_positive", "phi_k", "k_grid",
    "scatter_amplitudes", "continuity_residual",
]


# ======================================================================
# 1. 解析解: 方势垒透射系数 (闭式)
# ======================================================================
def t_exact(E, V0, a, m=MASS, hbar=HBAR):
    r"""方势垒 V(x)=V0 (|x|<a/2) 的精确透射系数.

        T(E) = 1 / ( 1 + (V0^2 / (4E(E-V0))) * sin^2(k2 a) ),   k2 = sqrt(2m(E-V0))/hbar

    当 E<V0 时 k2 为纯虚数, sin^2(k2 a) -> -sinh^2(kappa a), 得
        T = 1 / ( 1 + V0^2 sinh^2(kappa a) / (4E(V0-E)) )
    当 E>V0 时即为越顶透射 (含共振透射 T=1 的干涉振荡).

    E 可为标量或数组, a 也可为数组 (二者按 numpy 广播规则匹配). 返回与广播后
    形状相同的数组; 若输入均为标量则返回 Python float.
    """
    E_in = np.asarray(E, dtype=float)
    m_arr = np.asarray(m, dtype=float)
    scalar = (E_in.ndim == 0 and np.ndim(a) == 0 and np.ndim(V0) == 0
              and m_arr.ndim == 0)
    E1, a1, V1, m1 = np.broadcast_arrays(
        np.atleast_1d(E_in),
        np.atleast_1d(np.asarray(a, dtype=float)),
        np.atleast_1d(np.asarray(V0, dtype=float)),
        np.atleast_1d(m_arr))
    E = np.ascontiguousarray(E1, dtype=float)
    a = np.ascontiguousarray(a1, dtype=float)
    V0 = np.ascontiguousarray(V1, dtype=float)
    m = np.ascontiguousarray(m1, dtype=float)

    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        # ---- 越顶区 E > V0 : T = 1/(1 + V0^2 sin^2(k2 a)/(4E(E-V0))) ----
        k2a2 = 2.0 * m * (E - V0) * a ** 2 / hbar ** 2
        sin2 = np.sin(np.sqrt(np.abs(k2a2))) ** 2
        T_over = 1.0 / (1.0 + V0 ** 2 * sin2 / (4.0 * E * (E - V0)))
        # ---- 隧穿区 E < V0 : T = 1/(1 + V0^2 sinh^2(kappa a)/(4E(V0-E))) ----
        # sinh^2(x) = (e^x - e^-x)^2/4 ; 用 threshold 避免大 x 时上溢
        kappa_a = np.sqrt(2.0 * m * np.maximum(V0 - E, 0.0)) * a / hbar
        x = np.minimum(kappa_a, 400.0)
        e_minus = np.exp(-x)
        exp_x = np.exp(x)
        sh2 = 0.25 * (exp_x - e_minus) ** 2
        ratio = V0 ** 2 * sh2 / np.maximum(4.0 * E * np.maximum(V0 - E, 0.0), 1e-300)
        T_tun = 1.0 / (1.0 + ratio)
        # kappa a 超过 400 时 T 实际为 0 (exp(-800) 量级), 保留 T_tun 的极小值即可
        T = np.where(E < V0, T_tun, T_over)
    # 临界点 E->V0 : 1/(1 + m V0 a^2/(2 hbar^2))
    crit = np.abs(E - V0) < 1e-12
    T = np.where(crit, 1.0 / (1.0 + m * V0 * a ** 2 / (2.0 * hbar ** 2)), T)
    T = np.where(E <= 0.0, 0.0, T)
    T = np.clip(np.real(T), 0.0, 1.0)
    return float(T[0]) if scalar else T


def r_exact(E, V0, a, m=MASS, hbar=HBAR):
    """精确反射系数 R = 1 - T (保守系统, 无吸收)."""
    return 1.0 - t_exact(E, V0, a, m=m, hbar=hbar)


# ======================================================================
# 2. WKB 近似
# ======================================================================
def _broadcast_E_a(E, a, V0=None):
    """把能量、势垒宽度 (和可选垒高) 广播到同一形状; 返回 (E, a, scalar)."""
    Ei = np.asarray(E, dtype=float)
    args = [np.atleast_1d(Ei), np.atleast_1d(np.asarray(a, dtype=float))]
    if V0 is not None:
        args.append(np.atleast_1d(np.asarray(V0, dtype=float)))
    scalar = all(x.ndim == 0 for x in
                 [Ei, np.asarray(a), np.asarray(V0 if V0 is not None else 0.0)])
    out = np.broadcast_arrays(*args)
    Ea = np.ascontiguousarray(out[0], dtype=float)
    aa = np.ascontiguousarray(out[1], dtype=float)
    Va = None if V0 is None else np.ascontiguousarray(out[2], dtype=float)
    return Ea, aa, Va, scalar


def t_wkb(E, V0, a, m=MASS, hbar=HBAR):
    r"""标准 WKB 隧穿概率  T = exp( -(2/hbar) ∫ sqrt(2m(V(x)-E)) dx ).

    仅对 E < V0 有意义; E >= V0 时返回 1 (WKB 不描述越顶振荡).
    E, V0, a 可为标量或数组, 按 numpy 广播规则匹配.
    """
    E, a, V0, scalar = _broadcast_E_a(E, a, V0)
    kappa = np.sqrt(2.0 * m * np.maximum(V0 - E, 0.0)) / hbar
    T = np.where(E < V0, np.exp(-2.0 * kappa * a), 1.0)
    T = np.where(E <= 0.0, 0.0, T)
    return float(T[0]) if scalar else T


def t_wkb_simple(E, V0, a, m=MASS, hbar=HBAR):
    r"""带前置因子的常用近似  T ≈ 16E(V0-E)/V0^2 · exp(-2 kappa a)."""
    E, a, V0, scalar = _broadcast_E_a(E, a, V0)
    kappa = np.sqrt(2.0 * m * np.maximum(V0 - E, 0.0)) / hbar
    pref = 16.0 * E * np.maximum(V0 - E, 0.0) / V0 ** 2
    T = np.where(E < V0, pref * np.exp(-2.0 * kappa * a), 1.0)
    T = np.where(E <= 0.0, 0.0, T)
    T = np.clip(T, 0.0, 1.0)
    return float(T[0]) if scalar else T


# ======================================================================
# 3. 通用转移矩阵 (分段常数势, 独立验证用)
# ======================================================================
def scatter_amplitudes(E, betas, widths, m=MASS, hbar=HBAR, eps=1e-12):
    r"""分段常数势垒的透射/反射振幅 (以 sinh/cosh 为基的线性方程组直接求解).

    区域 0: x<0 (V=0), 区域 j: 势 V_j 宽 a_j (j=1..n), 区域 n+1: x>总宽 (V=0).
    分波写成
        psi_0 = e^{ik_0 x} + r e^{-ik_0 x}
        psi_{n+1} = t e^{ik_0 x}

    对每个垒内区域 (V>E, 令 kappa = sqrt(2m(V-E))/hbar), 取局部坐标
    s = x - x_{j-1} (该区域左端), 用数值稳定的实基
        psi_j(s) = A_j cosh(kappa_j s) + B_j sinh(kappa_j s)
        psi_j'(s) = kappa_j (A_j sinh(kappa_j s) + B_j cosh(kappa_j s))
    对 V<E 的区域 (令 q = sqrt(2m(E-V))/hbar) 取
        psi_j(s) = A_j cos(q_j s) + B_j sin(q_j s),  psi_j' = q_j(-A sin + B cos)

    【为什么不用 e^{±ikx} 复基】:
    kappa a 稍大时 e^{+kappa a} 会使线性方程组条件数按 e^{2 kappa a} 爆炸,
    即使方程精确成立, 解出的系数也会损失全精度 (实测残差 ~1e0).
    sinh/cosh 基的两个解在垒内都是 O(1) 量级, 条件数良好.

    未知量 x = (r, A_1, B_1, ..., A_n, B_n, t). 在 n+1 个界面上令 psi, psi' 连续,
    得到 2n+2 个方程:
        [左区域在界面处的 (psi, psi')] - [右区域] = 0,  入射项 e^{ik_0x} 移到右端.

    返回 (t, r, ks, coeffs, edges); coeffs[j] = (A_j, B_j) 为该区域局部基系数.
    """
    E = complex(E).real
    n = len(betas)
    for V in betas:                       # 规避 E = V_j 的临界退化
        if abs(E - V) < eps:
            E = V + eps
    k0 = np.sqrt(2.0 * m * E) / hbar
    edges = np.concatenate([[0.0], np.cumsum(widths)])    # n+1 个界面位置

    # 每个区域的基函数参数
    kinds, params = [], []
    for j in range(1, n + 1):
        V = betas[j - 1]
        if V > E:                          # 隧穿区: cosh/sinh
            kinds.append("cosh")
            params.append(np.sqrt(2.0 * m * (V - E)) / hbar)
        else:                              # 越顶区: cos/sin
            kinds.append("trig")
            params.append(np.sqrt(2.0 * m * (E - V)) / hbar)

    def basis(j, s):
        """区域 j (1..n) 在局部坐标 s 处的 (psi, psi') 关于 (A_j, B_j) 的 2x2 矩阵."""
        p = params[j - 1]
        if kinds[j - 1] == "cosh":
            ch, sh = np.cosh(p * s), np.sinh(p * s)
            return np.array([[ch, sh], [p * sh, p * ch]], dtype=complex)
        else:
            c, sn = np.cos(p * s), np.sin(p * s)
            return np.array([[c, sn], [-p * sn, p * c]], dtype=complex)

    nv = 2 * n + 2
    idx_r, idx_t = 0, nv - 1
    iA = lambda j: 2 * j - 1
    iB = lambda j: 2 * j

    A = np.zeros((nv, nv), dtype=complex)
    b = np.zeros(nv, dtype=complex)
    for e in range(n + 1):
        x = edges[e]
        jl, jr = e, e + 1
        row = 2 * e
        # ---- 左区域在 x 处 (若 jl==0 只有入射/反射波) ----
        if jl == 0:
            ei, er = np.exp(1j * k0 * x), np.exp(-1j * k0 * x)
            colL = np.array([[er], [-1j * k0 * er]], dtype=complex)
            bL = -np.array([[ei], [1j * k0 * ei]], dtype=complex)
        else:
            sL = x - edges[jl - 1]
            colL = basis(jl, sL)
            bL = np.zeros((2, 1), dtype=complex)
        # ---- 右区域在 x 处 ----
        if jr == n + 1:
            ei = np.exp(1j * k0 * x)
            colR = np.array([[-ei], [-1j * k0 * ei]], dtype=complex)
        else:
            sR = x - edges[jr - 1]
            colR = -basis(jr, sR)
        # 装配
        if jl == 0:
            A[row, idx_r] = colL[0, 0]
            A[row + 1, idx_r] = colL[1, 0]
        else:
            A[row, iA(jl)] = colL[0, 0]
            A[row, iB(jl)] = colL[0, 1]
            A[row + 1, iA(jl)] = colL[1, 0]
            A[row + 1, iB(jl)] = colL[1, 1]
        if jr == n + 1:
            A[row, idx_t] = colR[0, 0]
            A[row + 1, idx_t] = colR[1, 0]
        else:
            A[row, iA(jr)] = colR[0, 0]
            A[row, iB(jr)] = colR[0, 1]
            A[row + 1, iA(jr)] = colR[1, 0]
            A[row + 1, iB(jr)] = colR[1, 1]
        b[row] += bL[0, 0]
        b[row + 1] += bL[1, 0]

    sol = np.linalg.solve(A, b)
    r, t = sol[idx_r], sol[idx_t]
    coeffs = [(1.0 + 0j, complex(r))]
    for j in range(1, n + 1):
        coeffs.append((complex(sol[iA(j)]), complex(sol[iB(j)])))
    coeffs.append((complex(t), 0.0 + 0j))
    ks = [k0] + [complex(p) for p in params] + [k0]
    return complex(t), complex(r), ks, coeffs, edges


def transmission_matrix(E, betas, widths, m=MASS, hbar=HBAR):
    r"""分段常数势垒的透射系数 T = |t|^2.

    自检性质: (i) 各界面 psi 与 psi' 连续 (残差 ~1e-15);
              (ii) |t|^2 + |r|^2 = 1;
              (iii) 与解析闭式解 t_exact 一致到机器精度 (见 selftest.py).
    """
    t, r, ks, coeffs, edges = scatter_amplitudes(E, betas, widths, m=m, hbar=hbar)
    return float(np.abs(t) ** 2)


def continuity_residual(E, betas, widths, m=MASS, hbar=HBAR, eps=1e-12):
    """返回 (各界面上 |Δpsi|、|Δpsi'| 的最大值, |t|^2+|r|^2), 用于验证散射解."""
    t, r, ks, coeffs, edges = scatter_amplitudes(E, betas, widths, m=m, hbar=hbar, eps=eps)
    n = len(betas)
    E = float(np.real(E))
    for V in betas:
        if abs(E - V) < eps:
            E = V + eps

    def local_val(j, s):
        """区域 j 在局部坐标 s 处的 (psi, psi')."""
        if j == 0:
            return None
        V = betas[j - 1]
        A, B = coeffs[j]
        if V > E:
            p = np.sqrt(2.0 * m * (V - E)) / hbar
            ch, sh = np.cosh(p * s), np.sinh(p * s)
            return A * ch + B * sh, p * (A * sh + B * ch)
        else:
            p = np.sqrt(2.0 * m * (E - V)) / hbar
            c, sn = np.cos(p * s), np.sin(p * s)
            return A * c + B * sn, p * (-A * sn + B * c)

    k0 = np.sqrt(2.0 * m * E) / hbar
    worst = 0.0
    for j in range(n + 1):
        x = edges[j]
        if j == 0:
            psi_l = 1.0 + r
            d_l = 1j * k0 * (1.0 - r)
        else:
            psi_l, d_l = local_val(j, x - edges[j - 1])
        if j + 1 == n + 1:
            psi_r = t * np.exp(1j * k0 * x)
            d_r = 1j * k0 * psi_r
        else:
            psi_r, d_r = local_val(j + 1, x - edges[j])
        worst = max(worst, abs(psi_l - psi_r), abs(d_l - d_r))
    return float(worst), float(abs(t) ** 2 + abs(r) ** 2)


# ======================================================================
# 4. 初态与势
# ======================================================================
def rect_barrier(x, V0, a, x_c=0.0):
    """方势垒 V(x) = V0 (|x - x_c| < a/2)."""
    return np.where(np.abs(x - x_c) < a / 2.0, V0, 0.0)


def grid_barrier(x, V0, a, edge_smooth=1.5, x_c=0.0):
    r"""为 FFT 网格离散化准备的方势垒 (边缘做 dx 级平滑).

    【为什么必须平滑】
    分步傅里叶法里的势能以"逐格点乘相位"的方式精确作用, 因此网格上的离散
    方势垒带有锯齿状边缘. 对平面波基组而言, 阶跃势的边缘量化误差随 dx 只是
    缓慢振荡衰减 (实测误差 -4.2e-2 -> -1.5e-2 -> -6.3e-4 -> +6.5e-3, 非单调),
    无法用加密网格可靠收敛.
    把边缘用宽度 w = edge_smooth * dx 的 cos^2 斜坡平滑后, 数值透射率迅速收敛
    到连续极限 (实测 w = 1.5 dx 时各分辨率误差 < 1.2e-3, 细网格 < 5e-5),
    且 w -> 0 时势垒回到理想方势垒. 势垒内部宽度保持不变 (斜坡一半在内一半在外).

    参数 edge_smooth: 平滑宽度, 以格点间距 dx 为单位; 0 表示不平滑.
    """
    x = np.asarray(x, dtype=float)
    if edge_smooth <= 0:
        return rect_barrier(x, V0, a, x_c=x_c)
    dx = abs(x[1] - x[0])
    w = edge_smooth * dx
    ax = np.abs(x - x_c)
    half = a / 2.0
    V = np.zeros_like(x)
    V[ax <= half - w / 2.0] = V0
    sel = (ax > half - w / 2.0) & (ax < half + w / 2.0)
    V[sel] = V0 * 0.5 * (1.0 - np.cos(np.pi * (half + w / 2.0 - ax[sel]) / w))
    return V


def gaussian_packet(x, x0, sigma, k0, hbar=HBAR):
    r"""最小不确定度高斯波包:
        psi(x) = (2 pi sigma^2)^{-1/4} exp( -(x-x0)^2/(4 sigma^2) + i k0 x )
    平均动量 <p> = hbar k0, 动量不确定度 dp = hbar/(2 sigma)."""
    norm = (2.0 * np.pi * sigma ** 2) ** (-0.25)
    return norm * np.exp(-(x - x0) ** 2 / (4.0 * sigma ** 2) + 1j * k0 * x)


def packet_mean_energy(psi, x, V, hbar=HBAR, m=MASS):
    """<E> = <T> + <V>, 动能用谱方法精确计算."""
    dx = x[1] - x[0]
    k, dk = k_grid(x)
    pk = phi_k(psi, x, hbar=hbar)
    T = np.sum(np.abs(pk) ** 2 * (hbar ** 2 * k ** 2 / (2.0 * m))) * dk
    return float(T + np.sum(np.abs(psi) ** 2 * V) * dx)


# ======================================================================
# 5. 含时演化: 分步傅里叶法
# ======================================================================
def phi_k(psi, x, hbar=HBAR):
    r"""动量表象波函数 (正确归一化).

        phi(k) = (1/sqrt(2 pi)) ∫ psi(x) e^{-i k x} dx
    离散实现:  phi = FFT[psi] * dx / sqrt(2 pi)

    满足 Parseval:  ∫|phi(k)|^2 dk = ∫|psi(x)|^2 dx = 1.
    注意 numpy.fft.fft 不带任何归一化因子, 必须显式乘 dx/sqrt(2 pi),
    否则谱密度会整体差一个 2 pi 因子 (这会直接污染 <T>、<E>、<p> 等所有谱量).
    """
    dx = x[1] - x[0]
    return np.fft.fft(psi) * dx / np.sqrt(2.0 * np.pi)


def k_grid(x):
    """与 rfft/fft 对应的角波数网格和波数间隔 dk."""
    N = x.size
    dx = x[1] - x[0]
    return 2.0 * np.pi * np.fft.fftfreq(N, d=dx), 2.0 * np.pi / (N * dx)


def _absorb_mask(N, width, strength=2.0):
    r"""两端平滑吸收掩模 (模拟开放边界, 抑制 FFT 周期回绕).

    掩模在边界处为 0 且**梯度也为 0**, 向内部平滑升到 1:
        mask(i) = 1 - (1 - (i+0.5)/nw)^strength,   i = 0..nw-1 (边界起算)
    strength >= 2 时边界处一阶导为零, 不会像线性/正弦斜坡那样把波包截断出
    尖锐台阶, 从而避免在动量空间激发大量高频分量 (实测这会导致数个百分点
    的概率"凭空"丢失, 破坏守恒). 每步吸收极少量概率, 多次经过即可基本吸尽.
    """
    mask = np.ones(N)
    nw = int(width)
    if nw <= 0:
        return mask
    s = np.arange(nw)                       # 0 = 最外边界
    ramp = 1.0 - (1.0 - (s + 0.5) / nw) ** strength     # 0 -> 接近 1
    mask[:nw] = ramp[::-1]
    mask[-nw:] = ramp
    return mask


def split_operator_evolve(psi0, x, V, dt, n_steps, m=MASS, hbar=HBAR,
                          record_at=(), sample_at=(), sample_fn=None,
                          absorb_width=0, absorb_strength=1.0,
                          keep_k=False, barrier_span=(-10.0, 10.0)):
    r"""分步傅里叶 (split-operator) 求解  i hbar dψ/dt = H ψ.

    Strang 分裂, 二阶精度:
        ψ(t+dt) = e^{-iV dt/2h} · F^{-1}[ e^{-i hbar k^2 dt/2m} F[ · ] ]
                  · e^{-iV dt/2h} ψ(t)

    参数
    ----
    record_at : 记录完整波函数快照的步号 (做动画用)
    sample_at : 调用 sample_fn(step, t, psi) 做在线积分的步号
    keep_k    : 快照中是否附带动量谱
    absorb_width : 吸收层厚度 (格点数), 0 表示周期边界

    返回
    ----
    psi  : 末态
    snap : {'t': [...], 'psi': [...], 'k': ..., 'k_dist': [...]}
    diag : {'t','norm','x_mean','p_mean','p_left','p_mid','p_right','energy'}
    """
    x = np.asarray(x, dtype=float)
    N = x.size
    dx = x[1] - x[0]
    k, dk = k_grid(x)
    mask = _absorb_mask(N, absorb_width, absorb_strength)

    expK_full = np.exp(-1j * hbar * k ** 2 * dt / (2.0 * m))
    expV_half = np.exp(-1j * V * (dt / 2.0) / hbar)

    psi = np.asarray(psi0, dtype=complex).copy() * mask

    xa, xb = barrier_span
    sel_l = x < xa
    sel_m = (x >= xa) & (x <= xb)
    sel_r = x > xb

    snap = {"t": [], "psi": [], "k": np.fft.fftshift(k), "k_dist": []}
    diag = {key: [] for key in ("t", "norm", "x_mean", "p_mean",
                                "p_left", "p_mid", "p_right", "energy",
                                "absorbed_left", "absorbed_right")}
    # 吸收层内的区域与累计吸收概率的暂存量
    if absorb_width > 0:
        nw = int(absorb_width)
        sel_abs_l = x < (x[0] + nw * dx)
        sel_abs_r = x > (x[-1] - nw * dx)
    else:
        sel_abs_l = np.zeros(N, dtype=bool)
        sel_abs_r = np.zeros(N, dtype=bool)
    absorbed = {"left": 0.0, "right": 0.0, "prev_l": None, "prev_r": None}

    def measure(step, t, psi):
        dens = np.abs(psi) ** 2
        # 剩余概率密度 + 此前累计被吸收的概率 = 总概率 (应恒为 1)
        nrm = float(np.sum(dens) * dx) + absorbed["left"] + absorbed["right"]
        diag["t"].append(t)
        diag["norm"].append(nrm)
        diag["absorbed_left"].append(absorbed["left"])
        diag["absorbed_right"].append(absorbed["right"])
        diag["x_mean"].append(float(np.sum(x * dens) * dx))
        diag["p_left"].append(float(np.sum(dens[sel_l]) * dx))
        diag["p_mid"].append(float(np.sum(dens[sel_m]) * dx))
        diag["p_right"].append(float(np.sum(dens[sel_r]) * dx))
        if step == 0 or step % 200 == 0:
            pk = phi_k(psi, x, hbar=hbar)
            diag["p_mean"].append(float(np.sum(k * np.abs(pk) ** 2) * dk))
            diag["energy"].append(float(np.sum(np.abs(pk) ** 2 *
                                               (hbar ** 2 * k ** 2 / (2.0 * m))) * dk))
        else:
            diag["p_mean"].append(np.nan)
            diag["energy"].append(np.nan)

    rec_set = set(record_at)
    smp_set = set(sample_at)

    measure(0, 0.0, psi)
    if 0 in rec_set:
        snap["t"].append(0.0)
        snap["psi"].append(psi.copy())
        if keep_k:
            snap["k_dist"].append(np.abs(np.fft.fftshift(np.fft.fft(psi))) ** 2)
    if 0 in smp_set and sample_fn is not None:
        sample_fn(0, 0.0, psi)

    expK = expK_full
    for step in range(1, n_steps + 1):
        psi = expV_half * psi
        psi = np.fft.ifft(expK * np.fft.fft(psi))
        psi = expV_half * psi
        if absorb_width > 0:
            # 逐时间步累计被吸收层吞掉的概率 (左右分开记账, 保证概率守恒可核查)
            dens = np.abs(psi) ** 2
            wl = float(np.sum(dens[sel_abs_l]) * dx)
            wr = float(np.sum(dens[sel_abs_r]) * dx)
            if absorbed["prev_l"] is not None:
                absorbed["left"] += max(absorbed["prev_l"] - wl, 0.0)
                absorbed["right"] += max(absorbed["prev_r"] - wr, 0.0)
            absorbed["prev_l"], absorbed["prev_r"] = wl, wr
            psi = psi * mask
        if step in rec_set:
            snap["t"].append(step * dt)
            snap["psi"].append(psi.copy())
            if keep_k:
                snap["k_dist"].append(np.abs(np.fft.fftshift(np.fft.fft(psi))) ** 2)
        if step in smp_set:
            measure(step, step * dt, psi)
            if sample_fn is not None:
                sample_fn(step, step * dt, psi)

    return psi, snap, diag


# ======================================================================
# 6. 谱分解工具
# ======================================================================
def amplitude_weights(psi0, x, hbar=HBAR, m=MASS):
    r"""把初始波包分解为平面波分量.

    返回 (k_sorted, w_sorted, E_sorted), 其中 w = |phi(k)|^2 dk 是该格点
    代表的动量概率 (全部求和 = 1), 按 k 升序排列.
    """
    return _raw_weights(psi0, x, hbar=hbar, m=m)


def spectrum_weights(psi0, x, hbar=HBAR, m=MASS, k_cut=0.0):
    r"""把初始波包按平面波分解, 返回 (k, w, E), 按 k 升序排列.

    约定: w 是**逐格点的动量概率**, Σ w = ∫|phi(k)|^2 dk = 1 (无需再乘 dk).
    若给出 k_cut > 0, 则只保留 k > -k_cut 的分量并重新归一化, 同时返回被丢弃
    的权重, 供使用者判断该近似是否可靠.

    返回 (k, w, E, dropped)
    """
    ks, w, E = _raw_weights(psi0, x, hbar=hbar, m=m)
    dropped = 0.0
    if k_cut > 0.0:
        keep = ks > -k_cut
        dropped = float(np.sum(w[~keep]))
        w = np.where(keep, w, 0.0)
        tot = w.sum()
        if tot > 0:
            w = w / tot
    return ks, w, E, dropped


def spectrum_average_T(psi0, x, V0, a, hbar=HBAR, m=MASS, k_cut=0.0,
                       return_T=False):
    r"""入射波包的能量谱平均透射率 (精确的加权求和, 不需要再乘 dk):

        <T> = Σ_k w_k T(E_k) / Σ_k w_k

    w_k 为逐格点动量概率 (Σ w = 1), 因此这就是 ∫|phi(k)|^2 T(E_k) dk 的
    离散形式. 若波包几乎不含 k<0 分量, 也可用 2·Σ_{k>0} w_k T(E_k) 复核.
    return_T=True 时同时返回 T(E_k) 数组.
    """
    ks, w, E, dropped = spectrum_weights(psi0, x, hbar=hbar, m=m, k_cut=k_cut)
    T = np.asarray(t_exact(E, V0, a, m=m, hbar=hbar), dtype=float)
    val = float(np.sum(w * T) / np.sum(w))
    if return_T:
        return val, T
    return val


def spectrum_average_T_positive(psi0, x, V0, a, hbar=HBAR, m=MASS):
    """仅用 k>0 半边计算的谱平均, 用于与 spectrum_average_T 互相复核.

    对于 k0 >> sigma_k 的入射波包, k<0 的权重可以忽略,
    因此 Σ_{k>0} w_k T(E_k) 应当与全谱的加权平均一致.
    """
    ks, w, E, _ = spectrum_weights(psi0, x, hbar=hbar, m=m)
    T = np.asarray(t_exact(E, V0, a, m=m, hbar=hbar), dtype=float)
    pos = ks > 0
    return float(np.sum(w[pos] * T[pos]) / max(np.sum(w[pos]), 1e-300))


def _raw_weights(psi0, x, hbar=HBAR, m=MASS):
    """内部: 返回未截断的 (k, |phi(k)|^2 dk, E), 按 k 升序."""
    k, dk = k_grid(x)
    pk = phi_k(psi0, x, hbar=hbar)
    w = np.abs(pk) ** 2 * dk
    order = np.argsort(k)
    ks, ws = k[order], w[order]
    E = hbar ** 2 * ks ** 2 / (2.0 * m)
    return ks, ws, E

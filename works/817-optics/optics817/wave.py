# -*- coding: utf-8 -*-
"""第一章 光的电磁理论基础。

覆盖考点：
    * 光波的数学表示、相速度/群速度、时域与空域频谱
    * 反射定律、折射定律、菲涅耳公式（rs/rp/ts/tp、Rs/Rp）
    * 布儒斯特角、全反射与全反射相移
    * 偏振态的琼斯矢量/琼斯矩阵表示
"""
from __future__ import annotations

import numpy as np

C0 = 299792458.0  # 真空光速 m/s


# ---------------------------------------------------------------- 光波基本量
def wavelength_in_medium(lam0: float, n: float) -> float:
    """介质中波长 lambda = lambda0 / n。"""
    return lam0 / n


def phase_velocity(lam0: float, n: float) -> float:
    """相速度 v = c / n。"""
    return C0 / n


def wave_number(lam: float, n: float = 1.0) -> float:
    """波数 k = 2*pi*n/lambda0。"""
    return 2.0 * np.pi * n / lam


def plane_wave(z, t, lam0: float, n: float = 1.0, A: float = 1.0, phi0: float = 0.0):
    """沿 +z 传播的单色平面波 E(z,t) = A cos(kz - wt + phi0)（取实部）。"""
    k = wave_number(lam0, n)
    w = 2.0 * np.pi * C0 / lam0
    return A * np.cos(k * np.asarray(z) - w * np.asarray(t) + phi0)


def group_velocity(lam0: float, n: float, dn_dlam: float, lam_unit: str = "m") -> float:
    """群速度 vg = c / (n - lambda0 * dn/dlambda)（正常色散时 vg < c/n）。"""
    ng = n - lam0 * dn_dlam
    return C0 / ng


# ---------------------------------------------------------------- 菲涅耳公式
def fresnel(n1: float, n2: float, theta_i):
    """菲涅耳振幅系数与反射率/透射率。

    参数
    ----
    n1, n2 : 入射介质、折射介质折射率
    theta_i : 入射角（弧度），可为 numpy 数组

    返回 dict: rs, rp, ts, tp（复数，全反射时自动含相位）, Rs, Rp, Ts, Tp
    符号约定（与郁道银《工程光学》、石顺祥《物理光学与应用光学》一致）：
        rs = (n1 cos i - n2 cos t) / (n1 cos i + n2 cos t)
        rp = (n2 cos i - n1 cos t) / (n2 cos i + n1 cos t)
    光疏 -> 光密（n1<n2）正入射时 rs < 0，表示反射光有 pi 的半波损失。
    """
    th = np.asarray(theta_i, dtype=float)
    ci = np.cos(th)
    ct = np.sqrt(1.0 - (n1 * np.sin(th) / n2) ** 2 + 0j)  # 全反射时自动变虚数
    rs = (n1 * ci - n2 * ct) / (n1 * ci + n2 * ct)
    rp = (n2 * ci - n1 * ct) / (n2 * ci + n1 * ct)
    ts = 2.0 * n1 * ci / (n1 * ci + n2 * ct)
    tp = 2.0 * n1 * ci / (n2 * ci + n1 * ct)
    Rs, Rp = np.abs(rs) ** 2, np.abs(rp) ** 2
    return dict(
        rs=rs, rp=rp, ts=ts, tp=tp, Rs=Rs, Rp=Rp,
        Ts=1.0 - Rs, Tp=1.0 - Rp,  # 无吸收介质中 T = 1 - R
    )


def brewster_angle(n1: float, n2: float) -> float:
    """布儒斯特角 theta_B = arctan(n2/n1)（弧度），此时 rp = 0。"""
    return float(np.arctan(n2 / n1))


def critical_angle(n1: float, n2: float) -> float:
    """全反射临界角 theta_C = arcsin(n2/n1)，仅当 n1 > n2 时存在。"""
    if n1 <= n2:
        return float("nan")
    return float(np.arcsin(n2 / n1))


def tir_phase_shifts(n1: float, n2: float, theta_i):
    """全反射时的相移 delta_s、delta_p（弧度），满足 rs = exp(-i ds), rp = exp(-i dp)。

        tan(ds/2) = -sqrt(sin^2 i - n^2) / cos i
        tan(dp/2) = -sqrt(sin^2 i - n^2) / (n^2 cos i),   n = n2/n1
    两者之差 dp - ds 是菲涅耳菱体/相位延迟器的原理。
    """
    th = np.asarray(theta_i, dtype=float)
    n = n2 / n1
    s2 = np.clip(np.sin(th) ** 2 - n ** 2, 0.0, None)
    root = np.sqrt(s2)
    ds = 2.0 * np.arctan(root / np.cos(th))
    dp = 2.0 * np.arctan(root / (n ** 2 * np.cos(th)))
    return ds, dp


def reflectance_multilayer_normal(n_list, d_list, lam: float, pol: str = "s", theta0: float = 0.0):
    """多层膜反射率（特征矩阵法 / TMM），对应第四章光学薄膜。

    n_list : [n_incident, n_layer1, n_layer2, ..., n_substrate]
    d_list : 各膜层几何厚度（不含入射/出射介质），长度 = len(n_list) - 2
    pol    : 's' 或 'p'
    返回反射率 R（0~1）。
    """
    n_arr = np.asarray(n_list, dtype=float)
    n0, ns = n_arr[0], n_arr[-1]
    th0 = float(theta0)
    # 各界面折射角（斯涅尔定律，复数处理全反射）
    cos = [np.cos(th0)]
    for i in range(1, len(n_arr)):
        s = n_arr[0] * np.sin(th0) / n_arr[i]
        cos.append(np.sqrt(1.0 - s ** 2 + 0j))
    eta = (lambda c, nn: nn * c) if pol == "s" else (lambda c, nn: nn / c)

    M = np.eye(2, dtype=complex)
    for j, (nn, dd) in enumerate(zip(n_arr[1:-1], d_list)):
        cj = cos[j + 1]
        delta = 2.0 * np.pi * nn * dd * cj / lam
        e = eta(cj, nn)
        Mj = np.array(
            [[np.cos(delta), 1j * np.sin(delta) / e],
             [1j * e * np.sin(delta), np.cos(delta)]],
            dtype=complex,
        )
        M = M @ Mj
    e0, es = eta(cos[0], n0), eta(cos[-1], ns)
    A, B, C, D = M[0, 0], M[0, 1], M[1, 0], M[1, 1]
    num = e0 * A + e0 * es * B - C - es * D
    den = e0 * A + e0 * es * B + C + es * D
    return float(np.abs(num / den) ** 2)


def antireflection_thickness(lam0: float, n_film: float) -> float:
    """单层增透膜（1/4 波长）几何厚度 d = lambda0 / (4 n)。"""
    return lam0 / (4.0 * n_film)


def quarter_wave_reflectance(n0: float, n_film: float, ns: float):
    """单层 1/4 波长膜的反射率（正入射）。

        R = ((n0 ns - n_film^2) / (n0 ns + n_film^2))^2
    当 n_film = sqrt(n0 ns) 时 R = 0（完全增透）。
    """
    x = n0 * ns
    return float(((x - n_film ** 2) / (x + n_film ** 2)) ** 2)


# ---------------------------------------------------------------- 琼斯矩阵
def jones_linear(alpha: float, E0: float = 1.0):
    """线偏振光的琼斯矢量，振动方向与 x 轴夹角 alpha。"""
    return E0 * np.array([np.cos(alpha), np.sin(alpha)], dtype=complex)


def jones_circular(sign: int = +1, E0: float = 1.0):
    """圆偏振光，sign=+1 左旋（对应 exp(-i wt) 约定）。"""
    return E0 / np.sqrt(2.0) * np.array([1.0, sign * 1j])


def jones_elliptical(psi: float, chi: float, E0: float = 1.0):
    """椭圆偏振光：方位角 psi、椭率角 chi（chi=±45° 为圆偏振）。"""
    c, s = np.cos(chi), np.sin(chi)
    rot = np.array([[np.cos(psi), -np.sin(psi)], [np.sin(psi), np.cos(psi)]])
    return E0 * (rot @ np.array([c, 1j * s]))


def jones_linear_polarizer(alpha: float):
    """透振方向为 alpha 的线偏振器琼斯矩阵。"""
    c, s = np.cos(alpha), np.sin(alpha)
    return np.array([[c * c, c * s], [c * s, s * s]], dtype=complex)


def jones_waveplate(delta: float, theta: float):
    """相位延迟 delta、快轴与 x 轴夹角 theta 的波片琼斯矩阵。"""
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s], [s, c]])
    D = np.diag([np.exp(-0.5j * delta), np.exp(0.5j * delta)])
    return R @ D @ R.T


def jones_rotator(phi: float):
    """旋光介质（或坐标旋转）琼斯矩阵，转角 phi。"""
    c, s = np.cos(phi), np.sin(phi)
    return np.array([[c, -s], [s, c]], dtype=complex)


def malus(I0: float, theta):
    """马吕斯定律 I = I0 cos^2(theta)。theta 为检偏器与偏振方向的夹角。"""
    return I0 * np.cos(np.asarray(theta, dtype=float)) ** 2


def stokes_from_jones(J) -> np.ndarray:
    """由琼斯矢量给出斯托克斯参量 [S0, S1, S2, S3]。"""
    Ex, Ey = complex(J[0]), complex(J[1])
    S0 = abs(Ex) ** 2 + abs(Ey) ** 2
    S1 = abs(Ex) ** 2 - abs(Ey) ** 2
    S2 = 2.0 * (Ex * Ey.conjugate()).real
    S3 = 2.0 * (Ex * Ey.conjugate()).imag
    return np.array([S0, S1, S2, S3])


def polarization_ellipse(J):
    """由琼斯矢量返回偏振椭圆参数 (方位角 psi, 椭率角 chi, 旋向)。"""
    S = stokes_from_jones(J)
    psi = 0.5 * np.arctan2(S[2], S[1])
    chi = 0.5 * np.arcsin(np.clip(S[3] / S[0], -1.0, 1.0))
    hand = "左旋" if S[3] > 0 else ("右旋" if S[3] < 0 else "线偏振")
    return float(psi), float(chi), hand

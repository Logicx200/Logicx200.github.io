# -*- coding: utf-8 -*-
"""第三章 光的衍射。

覆盖考点：
    * 夫琅禾费单缝、圆孔（艾里斑、瑞利判据）、多缝、光栅（缺级、分辨本领）
    * 巴俾涅原理
    * 菲涅耳圆孔衍射（轴向强度、波带片）、菲涅耳直边衍射（Cornu 螺线）
    * 衍射的应用：光栅、波带片、小孔/细线直径与狭缝宽度测量
"""
from __future__ import annotations

import numpy as np
from scipy.special import fresnel as _scipy_fresnel  # 注意：返回 (S, C)

from .fourier_optics import angular_spectrum, fraunhofer_fft, fresnel_fft  # noqa: F401


# ---------------------------------------------------------------- 夫琅禾费
def single_slit_intensity(x, lam: float, a: float, z: float, I0: float = 1.0):
    """单缝夫琅禾费衍射：I = I0 sinc^2(pi a sin(theta)/lam)，sin(theta)≈x/z。

    暗纹条件 a sin(theta) = k lambda (k = ±1, ±2, ...)，中心亮纹半角宽 = lambda/a。
    """
    th = np.asarray(x, dtype=float) / z
    beta = np.pi * a * th / lam
    return I0 * np.sinc(beta / np.pi) ** 2


def circular_aperture_intensity(x, lam: float, D: float, z: float, I0: float = 1.0):
    """圆孔夫琅禾费衍射（艾里斑）：I = I0 [2 J1(u)/u]^2，u = pi D sin(theta)/lam。

    第一暗环 u = 3.8317 -> 角半径 theta1 = 1.22 lambda / D。
    """
    from scipy.special import j1

    th = np.asarray(x, dtype=float) / z
    u = np.pi * D * th / lam
    u = np.where(np.abs(u) < 1e-12, 1e-12, u)
    return I0 * (2.0 * j1(u) / u) ** 2


def airy_radius(lam: float, D: float, z: float) -> float:
    """艾里斑第一暗环半径 r = 1.22 lambda z / D。"""
    return 1.22 * lam * z / D


def rayleigh_angle(lam: float, D: float) -> float:
    """瑞利判据最小分辨角 theta = 1.22 lambda / D。"""
    return 1.22 * lam / D


def grating_intensity(x, lam: float, d: float, N: int, a: float | None = None,
                      z: float = 1.0, I0: float = 1.0):
    """多缝（光栅）夫琅禾费强度：干涉因子 × 衍射因子。

    主极大（光栅方程）d sin(theta) = m lambda；缺级条件 d/a = m/k（整数比）。
    干涉因子用稳定形式 (sin(Na)/(N sin a))^2，在 a → m*pi 处取极限 1。
    """
    th = np.asarray(x, dtype=float) / z
    alpha = np.pi * d * th / lam
    den = np.sin(alpha)
    small = np.abs(den) < 1e-9
    den_safe = np.where(small, 1.0, den)
    I = (np.sin(N * alpha) / (N * den_safe)) ** 2
    I = np.where(small, 1.0, I)
    if a is not None:
        beta = np.pi * a * th / lam
        I = I * np.sinc(beta / np.pi) ** 2
    return I0 * I


def grating_angle(m, lam: float, d: float):
    """光栅方程 d sin(theta) = m lambda 的解，返回 |sin(theta)|<=1 的 m 对应的角度。"""
    s = np.asarray(m, dtype=float) * lam / d
    return np.where(np.abs(s) <= 1.0, np.arcsin(np.clip(s, -1, 1)), np.nan)


def grating_resolving_power(m, N: int):
    """光栅分辨本领 R = lambda/dlambda = m N（m 为级次，N 为刻线总数）。"""
    return np.asarray(m) * N


def grating_max_order(lam: float, d: float) -> int:
    """给定光栅常数时可能出现的最高级次（不含零级）。"""
    return int(np.floor(d / lam))


def babinet_complement(I_screen):
    """巴俾涅原理：互补屏的衍射场之和等于自由场。

    自由场在几何阴影外强度为 I0，故 I_互补 = I0 - I_屏（对振幅相加后取模）。
    这里演示强度层面的常用结论。
    """
    return 1.0 - I_screen


# ---------------------------------------------------------------- 菲涅耳衍射
def fresnel_number(a: float, lam: float, z: float) -> float:
    """菲涅耳数 N = a^2 / (lambda z)（a 为孔径半径或半宽）。"""
    return a ** 2 / (lam * z)


def fresnel_zone_radius(z: float, lam: float, m: int) -> float:
    """第 m 个菲涅耳半波带半径 r_m = sqrt(m lambda z)。"""
    return float(np.sqrt(m * lam * z))


def circular_aperture_axial_intensity(z, a: float, lam: float, I0: float = 1.0):
    """菲涅耳圆孔衍射轴线上强度：I/I0 = 4 sin^2(pi a^2 / (2 lambda z))。

    当 a^2 = lambda z（恰好一个半波带）时 I = 4 I0，是“波带片增亮”的根据；
    当 a^2 = 2 lambda z 时为暗点（泊松亮斑的互补情形）。
    """
    z = np.asarray(z, dtype=float)
    return I0 * 4.0 * np.sin(np.pi * a ** 2 / (2.0 * lam * z)) ** 2


def zone_plate_focal_lengths(a: float, lam: float, n_max: int = 5):
    """波带片的各级焦距 f_m = a^2 / (m lambda)，m 为奇数（奇级次才有焦点）。"""
    m = np.arange(1, 2 * n_max, 2)
    return m, a ** 2 / (m * lam)


def fresnel_edge_intensity(x, lam: float, z: float, I0: float = 1.0):
    """菲涅耳直边衍射强度分布（直边在 x=0，x>0 为几何照明区）。

        I/I0 = 1/2 { [C(v) + 1/2]^2 + [S(v) + 1/2]^2 },  v = x sqrt(2/(lambda z))
    几何阴影边界 x=0 处 I = I0/4；照明区出现亮暗振荡并趋于 I0。
    """
    x = np.asarray(x, dtype=float)
    v = x * np.sqrt(2.0 / (lam * z))
    S, C = _scipy_fresnel(v)  # scipy 返回 (S, C)
    return I0 * 0.5 * ((C + 0.5) ** 2 + (S + 0.5) ** 2)


def cornu_spiral(v_max: float = 5.0, n: int = 2000):
    """Cornu 螺线：x = C(v), y = S(v)。直边衍射的振幅即螺线上两点的矢量。"""
    v = np.linspace(-v_max, v_max, n)
    S, C = _scipy_fresnel(v)
    return C, S, v


def circular_aperture_axial_zone_phasor(N_zone):
    """用振幅矢量法给出圆孔轴线上的归一化振幅（菲涅耳半波带法）。

        A/A0 = 1 + cos(pi N) * ... 简化形式：|A/A0| = |sin(pi N/2)| * 2
    返回归一化强度，与 circular_aperture_axial_intensity 一致。
    """
    N_zone = np.asarray(N_zone, dtype=float)
    return 4.0 * np.sin(np.pi * N_zone / 2.0) ** 2


def wire_diameter_from_diffraction(x_min: float, lam: float, z: float) -> float:
    """由细丝（巴俾涅）衍射中央亮纹半宽求直径：a = lambda z / x_min。"""
    return lam * z / x_min


def slit_width_from_diffraction(x_k: float, k: int, lam: float, z: float) -> float:
    """由第 k 级暗纹位置求缝宽：a = k lambda z / x_k。"""
    return k * lam * z / x_k

# -*- coding: utf-8 -*-
"""第二章 光的干涉。

覆盖考点：
    * 干涉基本条件、相干长度/相干时间
    * 双光束干涉（杨氏双缝，含单缝衍射包络、条纹间距）
    * 平行平板多光束干涉（爱里公式、精细度、法布里-珀罗）
    * 光学薄膜（增透膜、高反膜、干涉滤光片）—— 高反膜用 wave.reflectance_multilayer_normal
    * 典型干涉仪：迈克尔逊（等倾圆环、等厚直条纹）、牛顿环、马赫-曾德尔
"""
from __future__ import annotations

import numpy as np

from . import wave


# ---------------------------------------------------------------- 相干性
def coherence_length(lam0: float, dlam: float) -> float:
    """相干长度 L_c ≈ lambda0^2 / dlambda（dlam 为谱线宽度）。"""
    return lam0 ** 2 / dlam


def coherence_time(lam0: float, dlam: float) -> float:
    """相干时间 tau_c = L_c / c。"""
    return coherence_length(lam0, dlam) / wave.C0


# ---------------------------------------------------------------- 双光束干涉
def double_slit_intensity(x, lam: float, d: float, a: float | None = None,
                          z: float = 1.0, I0: float = 1.0):
    """杨氏双缝屏上强度分布（近轴 sin(theta) ≈ x/z）。

    参数
    ----
    x : 屏上坐标（m），数组
    d : 双缝间距（m）
    a : 单缝宽度（m）；给定时乘以单缝衍射包络 sinc^2，否则为纯 cos^2 条纹
    z : 缝到屏距离（m）
    """
    th = np.asarray(x, dtype=float) / z
    alpha = np.pi * d * th / lam
    I = np.cos(alpha) ** 2
    if a is not None:
        beta = np.pi * a * th / lam
        I = I * np.sinc(beta / np.pi) ** 2
    return I0 * I


def fringe_spacing(lam: float, d: float, z: float) -> float:
    """双缝干涉条纹间距 Dx = lambda * z / d。"""
    return lam * z / d


def n_slit_intensity(x, lam: float, d: float, N: int, a: float | None = None,
                     z: float = 1.0, I0: float = 1.0):
    """N 缝（光栅）干涉强度：主极大 + 次极大 + 缺级。

    干涉因子写成 (sin(Na)/(N sin a))^2 的稳定形式：主极大处取极限值 1，
    避免 sin(a) → 0 时的 0/0 放大成假尖峰。
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


# ---------------------------------------------------------------- 多光束干涉
def airy_transmission(delta, r: float):
    """平行平板多光束干涉透射率（爱里公式）。

        T = 1 / (1 + F sin^2(delta/2)),  F = 4r^2/(1-r^2)^2
    delta : 相邻两束光的相位差
    r     : 界面振幅反射率（无吸收时 R = r^2）
    """
    R = r ** 2
    F = 4.0 * R / (1.0 - R) ** 2
    return 1.0 / (1.0 + F * np.sin(np.asarray(delta) / 2.0) ** 2)


def airy_reflectance(delta, r: float):
    """多光束干涉反射率 R_plate = F sin^2(delta/2) / (1 + F sin^2(delta/2))。"""
    T = airy_transmission(delta, r)
    return 1.0 - T


def finesse(r):
    """精细度 F* = pi sqrt(R) / (1 - R)，R = r^2（r 可为数组）。"""
    R = np.asarray(r, dtype=float) ** 2
    return np.pi * np.sqrt(R) / (1.0 - R)


def fabry_perot_peak_width(lam0: float, n: float, d: float, r: float, theta: float = 0.0):
    """F-P 干涉仪透射峰半宽（波长域）dlam = FSR / F*。

    FSR = lambda0^2 / (2 n d cos(theta))，F* 为精细度。
    分辨率 lambda/dlam = m F*。
    """
    fsr = lam0 ** 2 / (2.0 * n * d * np.cos(theta))
    return fsr / finesse(r)


def fabry_perot_transmission_wavelength(lam, n: float, d: float, r: float,
                                        theta: float = 0.0, Tmax: float = 1.0):
    """给定波长数组，返回 F-P 透射谱（正入射或小角度）。"""
    delta = 4.0 * np.pi * n * d * np.cos(theta) / np.asarray(lam, dtype=float)
    return Tmax * airy_transmission(delta, r)


# ---------------------------------------------------------------- 薄膜
def thin_film_reflectance(lam, n0: float, n: float, ns: float, d: float,
                          theta0: float = 0.0, pol: str = "s"):
    """单层薄膜反射率（等倾干涉，含多次反射）。对应“增透膜/高反膜”。

    lam : 波长数组（m）
    n0, n, ns : 入射介质 / 膜层 / 基底折射率
    d   : 膜厚（m）
    pol : 's' 或 'p'
    """
    lam = np.atleast_1d(np.asarray(lam, dtype=float))
    out = np.empty_like(lam)
    s0 = n0 * np.sin(theta0)  # 斯涅尔不变量 n sin(theta)
    c0 = np.cos(theta0)
    cf = _cos_t(n, s0)
    for i, l in enumerate(lam):
        r1 = _interface_amplitude(n0, c0, n, cf, pol)          # 入射介质 -> 膜层
        r2 = _interface_amplitude(n, cf, ns, _cos_t(ns, s0), pol)  # 膜层 -> 基底
        delta = 4.0 * np.pi * n * cf * d / l
        r_tot = (r1 + r2 * np.exp(1j * delta)) / (1.0 + r1 * r2 * np.exp(1j * delta))
        out[i] = abs(r_tot) ** 2
    return out


def _cos_t(n_medium: float, s0: float) -> complex:
    """由斯涅尔不变量求折射角余弦（自动处理全反射的虚数情形）。"""
    return np.sqrt(1.0 - (s0 / n_medium) ** 2 + 0j)


def _interface_amplitude(n1, c1, n2, c2, pol):
    """由两侧折射率与折射角余弦给出界面振幅反射率。"""
    if pol == "s":
        return (n1 * c1 - n2 * c2) / (n1 * c1 + n2 * c2)
    return (n2 * c1 - n1 * c2) / (n2 * c1 + n1 * c2)


# ---------------------------------------------------------------- 典型干涉仪
def newton_rings_intensity(r, lam: float, R: float, I0: float = 1.0):
    """牛顿环（反射光）强度分布：I = I0 sin^2(pi r^2/(lambda R))。

    中心为暗斑；第 m 个暗环半径 r_m = sqrt(m lambda R)，亮环 r_m = sqrt((m+1/2) lambda R)。
    """
    return I0 * np.sin(np.pi * np.asarray(r, dtype=float) ** 2 / (lam * R)) ** 2


def newton_dark_radius(m, lam: float, R: float):
    """第 m 个暗环半径（m = 0,1,2,...）。"""
    return np.sqrt(np.asarray(m) * lam * R)


def newton_bright_radius(m, lam: float, R: float):
    """第 m 个亮环半径（m = 0,1,2,...）。"""
    return np.sqrt((np.asarray(m) + 0.5) * lam * R)


def michelson_circular_intensity(theta, d: float, lam: float, I0: float = 1.0):
    """迈克尔逊等倾干涉圆环：光程差 Delta = 2 d cos(theta)。

    中心级次 m0 = 2d/lambda 最大；d 每变化 lambda/2 条纹移动一条。
    """
    delta = 2.0 * d * np.cos(np.asarray(theta, dtype=float))
    return 0.5 * I0 * (1.0 + np.cos(2.0 * np.pi * delta / lam))


def michelson_circular_radii(k, d: float, lam: float):
    """第 k 个圆环（从中心向外数，k=1,2,...）的张角 theta_k。

    cos(theta_k) = (m0 - k) lambda / (2 d)，其中 m0 = 2d/lambda。
    """
    m0 = 2.0 * d / lam
    c = (m0 - np.asarray(k, dtype=float)) * lam / (2.0 * d)
    return np.arccos(np.clip(c, -1.0, 1.0))


def wedge_fringe_spacing(lam: float, alpha: float, n: float = 1.0) -> float:
    """等厚干涉（劈尖）条纹间距 Dx = lambda / (2 n alpha)，alpha 为劈角（弧度）。"""
    return lam / (2.0 * n * alpha)


def mach_zehnder_intensity(delta, I0: float = 1.0, visibility: float = 1.0):
    """马赫-曾德尔干涉仪输出：I = I0 [1 + V cos(delta)] / 2 形式（单臂）。"""
    return 0.5 * I0 * (1.0 + visibility * np.cos(np.asarray(delta, dtype=float)))


def visibility(I_max, I_min):
    """条纹可见度 V = (Imax - Imin) / (Imax + Imin)。"""
    I_max = np.asarray(I_max, dtype=float)
    I_min = np.asarray(I_min, dtype=float)
    return (I_max - I_min) / (I_max + I_min)


def visibility_two_sources(I1: float, I2: float):
    """两束光干涉的可见度 V = 2 sqrt(I1 I2)/(I1 + I2)。"""
    return 2.0 * np.sqrt(I1 * I2) / (I1 + I2)

# -*- coding: utf-8 -*-
"""傅里叶光学基础 + 通用光场传播（第三章第 5 节、也是仿真里最常用的工具）。

包含：
    * 角谱法传播（近场，精确）
    * 单次 FFT 菲涅耳传播（远场）
    * 透镜的傅里叶变换性质（4f 系统、空间滤波）
    * 衍射受限系统的相干传递函数 CTF 与调制传递函数 MTF
"""
from __future__ import annotations

import numpy as np


def grid(N: int, dx: float):
    """生成以 0 为中心的 N×N 坐标网格，返回 (X, Y, x)。"""
    x = (np.arange(N) - N // 2) * dx
    X, Y = np.meshgrid(x, x)
    return X, Y, x


def circ_aperture(N: int, dx: float, radius: float):
    """圆形孔径（hard aperture）复振幅，返回 (U, X, Y, x)。"""
    X, Y, x = grid(N, dx)
    U = ((X ** 2 + Y ** 2) <= radius ** 2).astype(complex)
    return U, X, Y, x


def rect_aperture(N: int, dx: float, wx: float, wy: float | None = None):
    """矩形孔径复振幅，半宽 wx（x 方向）、wy（y 方向）。"""
    wy = wx if wy is None else wy
    X, Y, x = grid(N, dx)
    U = ((np.abs(X) <= wx) & (np.abs(Y) <= wy)).astype(complex)
    return U, X, Y, x


def angular_spectrum(U0: np.ndarray, lam: float, z: float, dx: float):
    """角谱法传播距离 z（输出网格与输入相同，适合近场/菲涅耳区）。

    传递函数 H(fx,fy) = exp(i 2 pi z sqrt(1/lam^2 - fx^2 - fy^2))，
    倏逝波（fx^2+fy^2 > 1/lam^2）截断为 0。
    """
    N = U0.shape[0]
    fx = np.fft.fftfreq(N, d=dx)
    FX, FY = np.meshgrid(fx, fx)
    arg = 1.0 / lam ** 2 - FX ** 2 - FY ** 2
    kz = np.sqrt(np.clip(arg, 0.0, None)) * (arg > 0)
    H = np.exp(1j * 2.0 * np.pi * z * kz)
    U = np.fft.ifft2(np.fft.fft2(U0) * H)
    return U, dx


def fresnel_fft(U0: np.ndarray, lam: float, z: float, dx: float):
    """单次 FFT 菲涅耳衍射（远场），返回 (U, dx_out, x_out)。

        U(x,y) = e^{ikz}/(i lam z) e^{ik(x^2+y^2)/2z}
                 * FT{ U0(xi,eta) e^{ik(xi^2+eta^2)/2z} } |_{fx = x/(lam z)}
    输出采样间隔 dx_out = lam z / (N dx)，可据此校验采样是否足够。
    """
    N = U0.shape[0]
    k = 2.0 * np.pi / lam
    X, Y, _ = grid(N, dx)
    quad_in = np.exp(1j * k * (X ** 2 + Y ** 2) / (2.0 * z))
    A = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(U0 * quad_in))) * dx ** 2
    fx = np.fft.fftshift(np.fft.fftfreq(N, d=dx))
    x_out = lam * z * fx
    XO, YO = np.meshgrid(x_out, x_out)
    # 数值上 z 很大时 e^{ik(x^2+y^2)/2z} ~ 1；保留可避免相位跳变
    quad_out = np.exp(1j * k * (XO ** 2 + YO ** 2) / (2.0 * z))
    U = np.exp(1j * k * z) / (1j * lam * z) * quad_out * A
    return U, lam * z / (N * dx), x_out


def fraunhofer_fft(U0: np.ndarray, lam: float, z: float, dx: float):
    """严格夫琅禾费（远场）衍射：屏上复振幅正比于孔径函数的傅里叶变换。

    返回 (U, dx_out, x_out)；强度分布 = |U|^2。
    """
    N = U0.shape[0]
    k = 2.0 * np.pi / lam
    A = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(U0))) * dx ** 2
    fx = np.fft.fftshift(np.fft.fftfreq(N, d=dx))
    x_out = lam * z * fx
    XO, YO = np.meshgrid(x_out, x_out)
    U = np.exp(1j * k * z) / (1j * lam * z) * np.exp(1j * k * (XO ** 2 + YO ** 2) / (2 * z)) * A
    return U, lam * z / (N * dx), x_out


def lens_fourier(U0: np.ndarray, lam: float, f: float, dx: float):
    """透镜后焦面上的光场 = 输入场（紧贴透镜前）的傅里叶变换。

    这是“透镜能做傅里叶变换”的核心结论，是 4f 系统与空间滤波的基础。
    返回 (U_f, dx_f, x_f)。
    """
    N = U0.shape[0]
    k = 2.0 * np.pi / lam
    A = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(U0))) * dx ** 2
    fx = np.fft.fftshift(np.fft.fftfreq(N, d=dx))
    x_f = lam * f * fx
    XF, YF = np.meshgrid(x_f, x_f)
    U_f = np.exp(1j * k * f) / (1j * lam * f) * np.exp(1j * k * (XF ** 2 + YF ** 2) / (2 * f)) * A
    return U_f, lam * f / (N * dx), x_f


def four_f_system(U0: np.ndarray, lam: float, f: float, dx: float, mask=None):
    """4f 系统：物 -> 谱面（滤波）-> 像。

    U0 : 物平面光场   f : 两个透镜焦距
    mask: 谱面掩模（与谱面同形状的复数组），None 表示不滤波
    返回 (U_image, dx, x)
    """
    U_f, dx_f, x_f = lens_fourier(U0, lam, f, dx)
    if mask is not None:
        U_f = U_f * mask
    # 第二次傅里叶变换（含坐标反转：两次 FT 得到倒像）
    U_i, dx_i, x_i = lens_fourier(U_f, lam, f, dx_f)
    return U_i, dx_i, x_i


def ctf_circular(fx, fy, lam: float, D: float, f: float):
    """衍射受限系统（圆形光瞳）的相干传递函数：

        CTF(f) = 1,  |f| <= fc = D/(2 lam f)
               = 0,  其他
    """
    fc = D / (2.0 * lam * f)
    r = np.sqrt(np.asarray(fx) ** 2 + np.asarray(fy) ** 2)
    return (r <= fc).astype(float)


def otf_circular(f, fc):
    """衍射受限系统（圆形光瞳、非相干照明）的光学传递函数 OTF：

        OTF(nu) = (2/pi) [arccos(nu) - nu sqrt(1 - nu^2)],  nu = f/fc <= 1
    注意 OTF 的截止频率是 CTF 的两倍（2 fc），这是考试常考的对比。
    """
    nu = np.clip(np.abs(np.asarray(f, dtype=float)) / fc, 0.0, 1.0)
    return (2.0 / np.pi) * (np.arccos(nu) - nu * np.sqrt(1.0 - nu ** 2))


def otf_rect_1d(f, fc):
    """一维矩形光瞳的 OTF：三角形函数 1 - |f|/fc（|f| <= fc）。"""
    nu = np.abs(np.asarray(f, dtype=float)) / fc
    return np.clip(1.0 - nu, 0.0, None)

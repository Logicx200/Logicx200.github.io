# -*- coding: utf-8 -*-
"""
irsim.model —— 复杂大气环境下红外目标探测仿真（简化物理模型）

设计原则
--------
1. 所有物理量、假设、参数都显式写在代码里，便于在报告中声明适用范围。
2. 大气模块是"参数化"模型（Beer-Lambert + 气溶胶幂律 + 水汽连续吸收 + CO2 4.3um 带），
   不是逐线/带模型；正式版应替换为 libRadtran / MODTRAN 输出（接口保持不变）。
3. 性能模型采用经典 MRTD→f_max→N→TTPF 链（Ratches/Lloyd 框架），
   取代之前的"简化双判据"，可比性更好；TTP/NVThermIP 作为后续升级项。
4. 输出量：波段透过率、视在温差、系统 MTF、MRTD、f_max、周期数 N、
   探测概率 P_d(R)、R50/R90、探测距离等。

主要文献依据
------------
- Koschmieder 1924；Ångström 1929；Hess et al. 1998 (OPAC)；Shettle & Fenn 1979
- Fried 1966（湍流 MTF/r0）；ITU-R P.1817（Cn2）
- Johnson 1958；Ratches 1976（MRTD 静态模型）；Vollmerhausen et al. 2004（TTPF）
- HITRAN2020；Mlawer et al. 2012（水汽连续吸收，简化参数化）
"""

from dataclasses import dataclass
import numpy as np
from scipy.optimize import brentq

H_PLANCK = 6.62607015e-34
C_LIGHT = 2.99792458e8
K_BOLTZ = 1.380649e-23


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
@dataclass
class Sensor:
    D: float = 0.100            # 口径 m
    f: float = 0.250            # 焦距 m
    pitch: float = 15e-6        # 像元间距 m
    fill: float = 0.8           # 填充因子
    netd: float = 0.030         # K
    sigma_jitter: float = 0.02  # 视轴抖动 mrad
    f_elec: float = 120.0       # 电子学 MTF 截止频率 cycles/mrad
    k_mrtd: float = 2.5         # MRTD 标定系数（MRTD(0)=k*NETD）
    n50: float = 8.0            # Johnson/NVThermIP 识别阈值（cycles）
    beta_ttpf: float = 2.0      # TTPF 指数 E（需按数据集标定）
    n50_detect: float = 2.0     # 探测阈值

    @property
    def fnum(self) -> float:
        return self.f / self.D

    @property
    def ifov_mrad(self) -> float:
        return self.pitch / self.f * 1e3


@dataclass
class Target:
    size: float = 2.3           # 临界尺寸 m
    dT: float = 10.0            # 目标-背景温差 K
    area: float = 2.3 * 2.3     # 迎光面积 m^2


@dataclass
class Atmo:
    mor: float = 23.0           # 能见度 km
    alpha: float = 1.3          # Ångström 指数
    w: float = 1.5              # 可降水量 cm（垂直柱）
    cn2: float = 1e-14          # m^(-2/3)
    t_air: float = 300.0        # K
    h_scale: float = 2.0        # 水汽标高 km


BANDS = {
    "LWIR": dict(lo=8.0, hi=12.0, n=401),
    "MWIR": dict(lo=3.0, hi=5.0, n=401),
}


# --------------------------------------------------------------------------- #
# 辐射与大气
# --------------------------------------------------------------------------- #
def planck_dBdT(lam_um, T):
    """普朗克函数对温度的导数（用于波段加权）。"""
    lam = np.asarray(lam_um, dtype=float) * 1e-6
    x = H_PLANCK * C_LIGHT / (lam * K_BOLTZ * T)
    B = 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / np.expm1(x)
    return B * x / T * np.exp(x) / np.expm1(x)


def band_grid(band):
    b = BANDS[band]
    return np.linspace(b["lo"], b["hi"], b["n"])


def band_weights(lam, T=300.0):
    wgt = planck_dBdT(lam, T)
    return wgt / wgt.sum()


def h2o_shape(lam, band):
    """水汽吸收在波段内的相对谱形（窗区中心弱、边缘强），归一化到中心处为 1。"""
    lam_c = 10.0 if band == "LWIR" else 4.0
    half = 2.0 if band == "LWIR" else 1.0
    return 1.0 + 1.2 * ((lam - lam_c) / half) ** 2


def beta_spectrum(lam, atmo: Atmo, band):
    """总消光系数谱 [km^-1]：气溶胶 + 水汽连续吸收 + CO2 4.3um 带。"""
    # 气溶胶：Koschmieder + Ångström 幂律
    beta_aer = (3.912 / atmo.mor) * (0.55 / lam) ** atmo.alpha

    # 水汽：用等效密度 rho_v = w / H 表示（cm/km），连续吸收系数按波段取值
    # 系数为简化标定值，正式版应由 libRadtran/MODTRAN 提供
    rho_v = atmo.w / atmo.h_scale
    k_h2o = 0.045 if band == "LWIR" else 0.070   # cm^-1 per cm path column（标定值）
    beta_h2o = k_h2o * h2o_shape(lam, band) * rho_v

    beta_co2 = np.zeros_like(lam)
    if band == "MWIR":
        # 4.3 um CO2 带：洛伦兹近似，峰位 4.26 um，HWHM 0.05 um
        beta_co2 = 25.0 * 0.05 ** 2 / ((lam - 4.26) ** 2 + 0.05 ** 2)

    return beta_aer + beta_h2o + beta_co2


def band_state(atmo: Atmo, band, R_km):
    """计算某波段在距离 R 处的透过率与等效波长。"""
    lam = band_grid(band)
    beta = beta_spectrum(lam, atmo, band)
    tau_lam = np.exp(-beta * R_km)
    w = band_weights(lam)
    tau_band = float(np.sum(tau_lam * w))
    lam_eff = float(np.sum(lam * w))
    return dict(
        lam=lam, tau_lam=tau_lam, weights=w, beta=beta,
        tau_band=tau_band, lam_eff=lam_eff,
    )


def path_radiance_band(atmo: Atmo, band, R_km):
    """路径辐射（简化 LTE：L_path=(1-tau)B(T_air)），返回波段加权值（诊断用）。"""
    lam = band_grid(band)
    beta = beta_spectrum(lam, atmo, band)
    tau = np.exp(-beta * R_km)
    lam_m = lam * 1e-6
    x = H_PLANCK * C_LIGHT / (lam_m * K_BOLTZ * atmo.t_air)
    B = 2 * H_PLANCK * C_LIGHT ** 2 / lam_m ** 5 / np.expm1(x)
    w = band_weights(lam)
    return float(np.sum((1.0 - tau) * B * w))


# --------------------------------------------------------------------------- #
# 湍流
# --------------------------------------------------------------------------- #
def fried_r0(lam_um, cn2, L_m):
    lam = lam_um * 1e-6
    return 0.185 * lam ** 1.2 * (cn2 * L_m) ** (-0.6)


# --------------------------------------------------------------------------- #
# 传感器 MTF 与 MRTD
# --------------------------------------------------------------------------- #
def system_mtf(f, lam_um, r0, sensor: Sensor):
    """系统 MTF（f 单位 cycles/mrad）。"""
    f = np.asarray(f, dtype=float)
    fc = sensor.D / (lam_um * 1e-6 * 1000.0)   # 衍射截止 cycles/mrad
    nu = np.clip(f / fc, 0.0, 1.0)
    mtf_diff = np.where(nu < 1.0,
                        (2 / np.pi) * (np.arccos(nu) - nu * np.sqrt(1 - nu ** 2)),
                        0.0)
    mtf_det = np.abs(np.sinc(f * sensor.ifov_mrad))
    f_rad = f * 1000.0
    mtf_turb = np.exp(-3.44 * (lam_um * 1e-6 * f_rad / r0) ** (5 / 3))
    mtf_jit = np.exp(-2 * np.pi ** 2 * sensor.sigma_jitter ** 2 * f ** 2)
    mtf_elec = 1.0 / (1.0 + (f / sensor.f_elec) ** 2)
    mtf = mtf_diff * mtf_det * np.clip(mtf_turb, 0, 1) * mtf_jit * mtf_elec
    return np.clip(mtf, 0.0, 1.0), fc


def mrtd_curve(f, lam_um, r0, sensor: Sensor):
    """MRTD(f) = k*NETD/MTF_sys(f)（工程近似，k 需实测标定）。"""
    mtf, _ = system_mtf(f, lam_um, r0, sensor)
    return sensor.k_mrtd * sensor.netd / np.maximum(mtf, 1e-9)


def f_max_from_contrast(dT_app, lam_um, r0, sensor: Sensor, f_grid=None):
    """给定视在温差，求最高可分辨频率 f_max（cycles/mrad）。"""
    if dT_app <= 0:
        return 0.0
    if f_grid is None:
        fc = sensor.D / (lam_um * 1e-6 * 1000.0)
        f_grid = np.linspace(0.0, fc * 1.02, 600)
    mtf, _ = system_mtf(f_grid, lam_um, r0, sensor)
    mtf_req = sensor.k_mrtd * sensor.netd / dT_app
    if mtf_req >= mtf[0]:
        return 0.0
    ok = np.where(mtf >= mtf_req)[0]
    if len(ok) == 0:
        return 0.0
    i = ok[-1]
    if i >= len(f_grid) - 1:
        return float(f_grid[-1])
    x0, x1 = mtf[i], mtf[i + 1]
    frac = 0.0 if x1 == x0 else (mtf_req - x0) / (x1 - x0)
    return float(f_grid[i] + frac * (f_grid[i + 1] - f_grid[i]))


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #
def n_cycles(fmax, target: Target, R_km):
    """目标上的周期数 N = f_max[cyc/mrad] * theta[mrad]，theta = size/R_km。"""
    return fmax * target.size / R_km


def pd_ttpf(n, n50, beta=2.0):
    r = np.maximum(np.asarray(n) / n50, 1e-12)
    return r ** beta / (1 + r ** beta)


def evaluate_at_range(atmo: Atmo, band, R_km, sensor: Sensor, target: Target):
    """单点评估：返回该距离处的链路量。"""
    st = band_state(atmo, band, R_km)
    lam_eff = st["lam_eff"]
    r0 = fried_r0(lam_eff, atmo.cn2, max(R_km, 1e-6) * 1000.0)
    dT_app = st["tau_band"] * target.dT
    fmax = f_max_from_contrast(dT_app, lam_eff, r0, sensor)
    n = n_cycles(fmax, target, R_km)
    return dict(
        R_km=R_km, tau_band=st["tau_band"], lam_eff=lam_eff, r0=r0,
        dT_app=dT_app, fmax=fmax, n=n,
        pd=float(pd_ttpf(n, sensor.n50, sensor.beta_ttpf)),
        pd_detect=float(pd_ttpf(n, sensor.n50_detect, sensor.beta_ttpf)),
    )


def range_for_pd(atmo: Atmo, band, sensor: Sensor, target: Target,
                 target_pd=0.5, Rmin=0.05, Rmax=60.0, n50=None):
    """求达到给定 P_d 的作用距离（默认 R50 用 n50）。"""
    n50 = sensor.n50 if n50 is None else n50

    def g(R):
        ev = evaluate_at_range(atmo, band, R, sensor, target)
        return float(pd_ttpf(ev["n"], n50, sensor.beta_ttpf)) - target_pd

    g_lo = g(Rmin)
    g_hi = g(Rmax)
    if g_lo < 0:
        return float("nan")      # 最小距离也达不到
    if g_hi > 0:
        return float(Rmax)       # 超出搜索范围
    return float(brentq(g, Rmin, Rmax, xtol=1e-3, rtol=1e-4))


def pd_curve(atmo: Atmo, band, sensor: Sensor, target: Target,
             R_grid=None, n50=None):
    """P_d(R) 曲线。"""
    n50 = sensor.n50 if n50 is None else n50
    if R_grid is None:
        R_grid = np.linspace(0.2, 12.0, 120)
    out = []
    for R in R_grid:
        ev = evaluate_at_range(atmo, band, R, sensor, target)
        out.append(dict(R_km=R, tau_band=ev["tau_band"], dT_app=ev["dT_app"],
                        fmax=ev["fmax"], n=ev["n"],
                        pd=float(pd_ttpf(ev["n"], n50, sensor.beta_ttpf))))
    return out


# --------------------------------------------------------------------------- #
# 默认配置
# --------------------------------------------------------------------------- #
def default_config():
    return Sensor(), Target(), Atmo()

# -*- coding: utf-8 -*-
"""
irrecog.radiometry —— 普朗克辐射、波段加权、视在温度反演

约定
----
* 波长单位 μm，光谱辐亮度单位 W/(m²·sr·μm)，波段平均辐亮度单位 W/(m²·sr)。
* 普朗克公式（λ 用 μm）：

      B(λ,T) = c1 / λ⁵ / (e^{c2/(λT)} − 1)
      c1 = 2hc² × 1e24 = 1.191042972e8   W·μm⁴/(m²·sr)
      c2 = hc/k × 1e6  = 14387.76877     μm·K

  校准核验：B(10 μm, 300 K) = 9.924 W/(m²·sr·μm)；∫₀^∞ B dλ = σT⁴/π（数值相对误差 6e-6，见 06_校验/公式校准报告.md）。

* 波段加权：w(λ) ∝ (dB/dT)(λ, T_ref) · Δλ。物理含义：探测器收到的目标-背景辐亮度差
  在小温差下正比于 dB/dT，故按 dB/dT 加权等价于"对比度加权"，是红外波段平均的标准做法
  （Lloyd 1975）。参考温度取 **场景背景温度**（默认 293.15 K = 20 ℃），不再固定 288.15 K；
  这样 w 与场景热状态自洽，对波段平均与视在温度反演均更准确。
  软件只给出平坦显示波段、无光谱响应函数，因此不额外引入响应曲线——该近似已在
  参数依据登记表中登记。
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import params
from .params import H_PLANCK, C_LIGHT, K_BOLTZ

#: 默认参考温度：20 ℃ 背景（场景可覆盖）
T_REF_K = params.T_REF_WEIGHT_K
_LUT_T_MIN, _LUT_T_MAX, _LUT_N = 100.0, 1000.0, 4501


def planck(lam_um, T_K):
    """普朗克光谱辐亮度 W/(m²·sr·μm)（支持广播）。

    注意单位：公式按波长(m)给 W/(m²·sr·m)，换算到"每 μm"需再乘 1e-6。
    """
    lam = np.asarray(lam_um, dtype=float) * 1e-6
    T = np.asarray(T_K, dtype=float)
    x = np.clip(H_PLANCK * C_LIGHT / (lam * K_BOLTZ * T), 0.0, 700.0)
    return 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / np.expm1(x) * 1e-6


def d_planck_dT(lam_um, T_K):
    """dB/dT = B·x·e^x/(e^x−1)/T，单位 W/(m²·sr·μm·K)，x=c2/(λT)。"""
    lam = np.asarray(lam_um, dtype=float) * 1e-6
    T = np.asarray(T_K, dtype=float)
    x = np.clip(H_PLANCK * C_LIGHT / (lam * K_BOLTZ * T), 0.0, 700.0)
    B = 2 * H_PLANCK * C_LIGHT ** 2 / lam ** 5 / np.expm1(x)
    return B * x * np.exp(x) / np.expm1(x) / T * 1e-6


def band_weights(lam_um, T_ref=T_REF_K):
    """波段对比度加权权重（归一到 Σw = 1），自动处理非均匀波长网格。

    w_i ∝ (dB/dT)(λ_i, T_ref) · Δλ_i，Δλ 由相邻点差分得到（梯形积分离散权）。
    因此波段平均等价于 ``∫ (dB/dT)·f dλ / ∫ (dB/dT) dλ``。
    """
    lam = np.asarray(lam_um, dtype=float)
    w = np.asarray(d_planck_dT(lam, T_ref), dtype=float)
    dlam = np.abs(np.gradient(lam)) if lam.size > 1 else np.ones_like(lam)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0) * dlam
    s = float(w.sum())
    return w / s if s > 0 else np.full(len(w), 1.0 / len(w))


@dataclass
class BandContext:
    """一个波段的光谱网格、权重与"辐亮度→视在温度"查找表。构造一次、复用全程。"""
    band: str
    lam_um: np.ndarray
    w: np.ndarray
    t_ref_k: float = T_REF_K
    lut_T: np.ndarray = field(repr=False, default=None)
    lut_L: np.ndarray = field(repr=False, default=None)

    def __post_init__(self):
        self.lam_um = np.asarray(self.lam_um, dtype=float)
        self.w = np.asarray(self.w, dtype=float)
        self.lut_T = np.linspace(_LUT_T_MIN, _LUT_T_MAX, _LUT_N)
        B = planck(self.lam_um[:, None], self.lut_T[None, :])       # (Nz, Nt)
        self.lut_L = (B * self.w[:, None]).sum(axis=0)              # 单调递增

    def band_average(self, spectral) -> float:
        return float(np.sum(np.asarray(spectral, dtype=float) * self.w))

    def t_app(self, L_band) -> float:
        """波段辐亮度 → 等效黑体温度 K。"""
        L = float(np.clip(L_band, self.lut_L[0], self.lut_L[-1]))
        return float(np.interp(L, self.lut_L, self.lut_T))

    def blackbody_band(self, T_K) -> float:
        """黑体波段辐亮度 W/(m²·sr)。"""
        return float(np.sum(self.w * planck(self.lam_um, T_K)))

    def radiance(self, T_K, eps, tau_lam, l_path_lam) -> float:
        """表面辐亮度（自发射项）：L = Σ w·(ε·B(λ,T)·τ(λ) + L_path(λ))。

        仅供"仅自发射"的近似/诊断使用；正式链路用 :meth:`surface_radiance`
        （含反射项与背景黑体环境辐亮度）。
        """
        B = planck(self.lam_um, T_K)
        return float(np.sum(self.w * (eps * B * tau_lam + l_path_lam)))

    def surface_radiance(self, t_surface_k, eps, tau_lam, l_path_lam,
                         t_ambient_k) -> float:
        """不透明表面在传感器处的波段辐亮度（含反射项）。

            L = Σ w·{ [ε·B(λ,T_s) + (1−ε)·B(λ,T_amb)]·τ(λ) + L_path(λ) }

        其中环境辐亮度按温度 T_amb 的黑体处理（T_amb 取背景温度，即目标四周地物
        与背景同温的热平衡近似）。该式与背景辐亮度
        L_b = Σ w·{[ε_b·B(T_b)+(1−ε_b)·B(T_amb)]·τ + L_path}（B(T_amb)=B(T_b) 时
        化简为 B(T_b)·τ+L_path）相减后严格得到
            ΔL = ε_t·Σ w·[B(λ,T_t) − B(λ,T_b)]·τ(λ)
        即对比度只由目标发射率与真实温差决定——这修正了原"目标/背景各自用 ε 乘
        黑体而无反射项"导致的热交叉位置偏移。
        """
        B_s = planck(self.lam_um, t_surface_k)
        B_amb = planck(self.lam_um, t_ambient_k)
        L = (eps * B_s + (1.0 - eps) * B_amb) * np.asarray(tau_lam, float) \
            + np.asarray(l_path_lam, float)
        return float(np.sum(self.w * L))

    def contrast_radiance(self, t_target_k, t_bg_k, eps_t, tau_lam) -> float:
        """目标相对背景的波段辐亮度差 ΔL = ε_t·Σw[B(T_t)−B(T_b)]τ（解析等价式）。"""
        dL = eps_t * (planck(self.lam_um, t_target_k) - planck(self.lam_um, t_bg_k))
        return float(np.sum(self.w * dL * np.asarray(tau_lam, float)))


_CTX_CACHE: dict = {}


def get_band_context(band: str, lam_um: np.ndarray, t_ref_k: float = T_REF_K) -> BandContext:
    """按（波段, 网格, 参考温度）缓存 BandContext（LUT 只算一次）。"""
    key = (band, len(lam_um), float(lam_um[0]), float(lam_um[-1]), round(float(t_ref_k), 4))
    ctx = _CTX_CACHE.get(key)
    if ctx is None:
        ctx = BandContext(band=band, lam_um=lam_um,
                          w=band_weights(lam_um, t_ref_k), t_ref_k=float(t_ref_k))
        _CTX_CACHE[key] = ctx
    return ctx

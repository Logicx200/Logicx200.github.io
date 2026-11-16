# -*- coding: utf-8 -*-
"""
irrecog.sensor —— 红外成像传感器模型：光学链自洽生成、MTF 链、MRTD、f_max

模型链（Ratches/Lloyd 框架）
---------------------------
1. 由软件实测 FOV/像元数推出 IFOV = FOV_h / N_h；由像元间距 f = p / IFOV；
   由 F# 得口径 D = f / F#。三者在几何上自洽，避免"口径-焦距-IFOV 互不相容"。
2. 系统 MTF(f) = 衍射 × 探测器 sinc × 视线抖动 × 湍流 × 电子学。
   f 单位 cycles/mrad，与目标角尺寸 mrad 相乘直接得到目标上的周期数 N。
3. MRTD(f) = k · NETD / MTF(f)（工程近似；k 即等效所需信噪比，登记为工程设定，k=2.5，
   对应 Ratches/Lloyd 框架中"低频 MRTD 约为 NETD 的 2–3 倍"的量级，需实测标定）。
4. 给定视在温差 ΔT_app，f_max 由 MRTD(f_max) = τ_opt · |ΔT_app| 求得；
   上限取 min(Nyquist, 衍射截止)。ΔT_app ≤ k·NETD/τ_opt 时 f_max = 0，
   这就是"对比度地板"——无论多近都不可识别。
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import params


@dataclass(frozen=True)
class Sensor:
    band: str = "MWIR"
    fov_h_deg: float = 3.75
    fov_v_deg: float = 3.0
    npx_h: int = 1024
    npx_v: int = 768
    pitch_m: float = 28.7e-6
    f_m: float = 0.449
    D_m: float = 0.1497
    netd_k: float = 25e-3
    tau_opt: float = 0.80
    jitter_mrad: float = 0.020
    k_mrtd: float = 2.5
    f_elec_cyc_mrad: float = 120.0
    cap_nyquist: bool = True
    platform_h_m: float = 8000.0

    # ---- 派生几何量 ----
    @property
    def ifov_mrad(self) -> float:
        return float(np.deg2rad(self.fov_h_deg) / self.npx_h * 1e3)

    @property
    def ifov_urad(self) -> float:
        return self.ifov_mrad * 1e3

    @property
    def f_number(self) -> float:
        return self.f_m / self.D_m

    @property
    def f_nyq_cyc_mrad(self) -> float:
        """采样 Nyquist 频率（1/(2·IFOV)）。"""
        return 1.0 / (2.0 * self.ifov_mrad)

    @property
    def delta_t_floor_k(self) -> float:
        """对比度地板：ΔT_app ≤ k·NETD 时 f_max=0，任何距离都识别不了。"""
        return self.k_mrtd * self.netd_k

    def f_cut_diffraction(self, lam_um: float) -> float:
        """衍射截止频率 cycles/mrad（圆孔非相干截止 D/λ）。"""
        return self.D_m / (lam_um * 1e-6) * 1e-3

    def f_upper(self, lam_um: float) -> float:
        """f_max 的物理上限：Nyquist（采样）与衍射截止取小。"""
        fc = self.f_cut_diffraction(lam_um)
        return min(self.f_nyq_cyc_mrad, fc) if self.cap_nyquist else fc

    # ---- MTF ----
    def mtf(self, f_cyc_mrad, lam_um: float, r0_m: Optional[float] = None) -> np.ndarray:
        f = np.atleast_1d(np.asarray(f_cyc_mrad, dtype=float))
        fc = self.f_cut_diffraction(lam_um)
        nu = np.clip(f / fc, 0.0, 1.0)
        mtf_diff = np.where(nu < 1.0,
                            (2.0 / np.pi) * (np.arccos(nu) - nu * np.sqrt(np.maximum(1 - nu ** 2, 0.0))),
                            0.0)
        x = f * self.ifov_mrad
        mtf_det = np.where(np.abs(x) < 1e-12, 1.0, np.abs(np.sin(np.pi * x) / (np.pi * np.where(x == 0, 1, x))))
        mtf_jit = np.exp(-2.0 * np.pi ** 2 * self.jitter_mrad ** 2 * f ** 2)
        if r0_m is not None and np.isfinite(r0_m) and r0_m > 0:
            mtf_turb = np.exp(-3.44 * (lam_um * 1e-6 * f * 1e3 / r0_m) ** (5.0 / 3.0))
        else:
            mtf_turb = np.ones_like(f)
        mtf_elec = 1.0 / (1.0 + (f / self.f_elec_cyc_mrad) ** 2)
        return np.clip(mtf_diff * mtf_det * mtf_jit * mtf_turb * mtf_elec, 0.0, 1.0)

    def mrtd(self, f_cyc_mrad, lam_um: float, r0_m: Optional[float] = None) -> np.ndarray:
        mtf = self.mtf(f_cyc_mrad, lam_um, r0_m)
        return self.k_mrtd * self.netd_k / np.maximum(mtf, 1e-12)

    # ---- f_max ----
    def f_max(self, d_t_app_k: float, lam_um: float, r0_m: Optional[float] = None,
              n_grid: int = 600) -> float:
        """给定视在温差，返回最高可分辨频率 cycles/mrad；不可分辨时返回 0。"""
        if not np.isfinite(d_t_app_k):
            return 0.0
        d_eff = self.tau_opt * abs(float(d_t_app_k))     # 光学透过率折减（探测器级 NETD）
        if d_eff <= self.delta_t_floor_k:
            return 0.0
        f_hi = self.f_upper(lam_um)
        if f_hi <= 0:
            return 0.0
        fg = np.linspace(0.0, f_hi, n_grid)
        mtf = self.mtf(fg, lam_um, r0_m)
        req = self.k_mrtd * self.netd_k / d_eff
        ok = np.where(mtf >= req)[0]
        if len(ok) == 0:
            return 0.0
        i = int(ok[-1])
        if i >= n_grid - 1:
            return float(f_hi)
        y0, y1 = float(mtf[i]), float(mtf[i + 1])
        frac = 0.0 if y1 == y0 else (req - y0) / (y1 - y0)
        return float(fg[i] + np.clip(frac, 0.0, 1.0) * (fg[i + 1] - fg[i]))


def fried_r0(lam_um: float, cn2: float, path_m: float) -> float:
    """Fried 相干直径 r0 = (0.423 k² Cn² L)^(-3/5)；Cn²=0 时返回 inf。"""
    if cn2 is None or not np.isfinite(cn2) or cn2 <= 0 or path_m <= 0:
        return float("inf")
    k = 2.0 * np.pi / (lam_um * 1e-6)
    return float((0.423 * k ** 2 * cn2 * path_m) ** (-0.6))


_DERIVED_KEYS = {"f_number", "frame_hz", "depression_deg"}


def make_sensor(band: str = "MWIR", preset: str = "RECOG", **overrides) -> Sensor:
    """按参考系统预设构造传感器（preset: RECOG 识别通道 / SEARCH 搜索通道）。"""
    if preset not in params.SENSOR_PRESETS:
        raise KeyError(f"未知传感器预设: {preset}")
    base = dict(params.SENSOR_PRESETS[preset])
    base["band"] = band
    base.update(overrides)
    fields = set(Sensor.__dataclass_fields__)
    unknown = set(base) - fields
    if unknown:
        raise TypeError(f"make_sensor 收到未知字段: {sorted(unknown)}")
    return Sensor(**base)

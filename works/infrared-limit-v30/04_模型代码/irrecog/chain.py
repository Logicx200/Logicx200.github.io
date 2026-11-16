# -*- coding: utf-8 -*-
"""
irrecog.chain —— 单点正向评估：大气 → 辐亮度 → 视在温差 → 传感器 → 任务概率

一次评估的完整链路
-----------------
1. ``atmosphere.spectral_state`` 给出斜程 τ(λ)、L_path(λ) 与斜距；
2. 目标/背景波段辐亮度（含反射项，环境辐亮度按背景黑体处理）::

       L_t = Σ w·{[ε_t·B(λ,T_t) + (1−ε_t)·B(λ,T_b)]·τ(λ) + L_path(λ)}
       L_b = Σ w·{[ε_b·B(λ,T_b) + (1−ε_b)·B(λ,T_b)]·τ(λ) + L_path(λ)}
           = Σ w·[B(λ,T_b)·τ(λ) + L_path(λ)]

   相减严格得 ΔL = ε_t·Σ w·[B(T_t)−B(T_b)]·τ，热交叉严格发生在 ΔT=0；
3. 由波段辐亮度反查等效黑体温度，得到视在温差 ΔT_app；
4. 湍流 r0 → 系统 MTF → MRTD(f)=k·NETD/MTF(f) → f_max（受 Nyquist/衍射/对比度三重限制）；
5. 目标角尺寸 θ = D_eff / R_slant（m/km ≡ mrad），周期数 N = f_max·θ；
6. TTPF：P = (N/N50)^E / (1 + (N/N50)^E)，按探测/识别/辨认三个 N50 分别给出。

缓存策略
--------
光谱大气是最贵的一步（0.05 cm⁻¹ × 40 层），但评估只需其**波段标量**：
S_t=Σw·B(T_t)τ、S_b=Σw·B(T_b)τ、L_path、τ_band、λ_eff、r_slant。因此把
"大气 + 波段积分"的结果按 (光谱大气参数, 距离, 高度, 目标/背景温度, 发射率)
缓存为元组（每条 ~百字节），而不是缓存完整光谱数组（每条 ~1 MB）——这样
全量 2 万级唯一状态的内存占用从 GB 级降到 MB 级。
"""

from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

import numpy as np

from . import atmosphere, params, probability, radiometry, sensor as sensor_mod, target as target_mod

_EPS = 1e-6


@dataclass(frozen=True)
class Scenario:
    """一个完整工况：传感器 + 目标 + 大气。"""
    target_key: str = "F16"
    target_temp_c: float = 40.0
    bg_temp_c: float = 20.0
    aod550: float = 0.587
    alpha: float = 1.30
    pwv_cm: float = 1.28
    cn2: float = 1e-15
    size_rule: str = "sqrt_area"
    n50_set: str = "NVESD"
    eps_t: Optional[float] = None          # None → 用目标模型默认发射率
    sensor: sensor_mod.Sensor = field(default_factory=lambda: sensor_mod.make_sensor("MWIR"))

    # ---- 便捷派生 ----
    @property
    def band(self) -> str:
        return self.sensor.band

    @property
    def atmo(self) -> atmosphere.Atmo:
        b = params.ATMOS_BASE
        return atmosphere.Atmo(aod550=self.aod550, alpha=self.alpha,
                               pwv_cm=self.pwv_cm, cn2=self.cn2,
                               h_aer_km=float(b["h_aer_km"]),
                               t0_c=float(b["t0_c"]), p0_hpa=float(b["p0_hpa"]),
                               h_wv_km=float(b["h_wv_km"]),
                               lapse_k_per_km=float(b["lapse_k_per_km"]))

    @property
    def target(self) -> target_mod.Target:
        return target_mod.get_target(self.target_key, self.size_rule)

    @property
    def dT_intrinsic_K(self) -> float:
        return self.target_temp_c - self.bg_temp_c

    def with_(self, **kw) -> "Scenario":
        return replace(self, **kw)

    def with_sensor(self, **kw) -> "Scenario":
        return replace(self, sensor=replace(self.sensor, **kw))


# --------------------------------------------------------------------------- #
# 波段标量缓存（大气+波段积分）
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=200000)
def _band_quantities(band: str, aod550: float, alpha: float, pwv_cm: float,
                     h_aer_km: float, t0_c: float, p0_hpa: float,
                     r_ground_km: float, z_target_m: float, z_sensor_m: float,
                     t_t_k: float, t_b_k: float, eps_t: float, eps_b: float):
    """返回 (L_t, L_b, S_t, S_b, L_path, t_app_t, t_app_b, dT_app, lam_eff,
    tau_band, r_slant_km, r_ground_km)。

    同一大气参数下不同目标温度/发射率复用同一份光谱状态（由 atmosphere 内部
    的截面缓存承担），本缓存只存标量，开销极小。
    """
    atmo = atmosphere.Atmo(aod550=aod550, alpha=alpha, pwv_cm=pwv_cm,
                           h_aer_km=h_aer_km, t0_c=t0_c, p0_hpa=p0_hpa)
    st = atmosphere.spectral_state(atmo, band, r_ground_km, z_target_m, z_sensor_m,
                                   with_components=False)
    lam = np.asarray(st["lam_um"], dtype=float)
    tau = np.asarray(st["tau_lam"], dtype=float)
    lp = np.asarray(st["l_path_lam"], dtype=float)
    ctx = radiometry.get_band_context(band, lam, t_b_k)
    w = ctx.w
    b_t = radiometry.planck(lam, t_t_k)
    b_b = radiometry.planck(lam, t_b_k)
    s_t = float(np.sum(w * b_t * tau))
    s_b = float(np.sum(w * b_b * tau))
    l_path = float(np.sum(w * lp))
    l_t = eps_t * s_t + (1.0 - eps_t) * s_b + l_path
    l_b = eps_b * s_b + (1.0 - eps_b) * s_b + l_path
    t_app_t = ctx.t_app(l_t)
    t_app_b = ctx.t_app(l_b)
    lam_eff = float(np.sum(w * lam))
    return (float(l_t), float(l_b), float(s_t), float(s_b), float(l_path),
            float(t_app_t), float(t_app_b), float(t_app_t - t_app_b),
            float(lam_eff), float(st["tau_band"]),
            float(st["r_slant_km"]), float(r_ground_km))


def band_quantities(scn: Scenario, r_ground_km: float) -> tuple:
    """按场景取（并缓存）波段标量。"""
    tgt = scn.target
    eps_t = tgt.eps if scn.eps_t is None else float(scn.eps_t)
    eps_b = float(params.BACKGROUND["eps"])
    b = params.ATMOS_BASE
    r = float(round(max(r_ground_km, 1e-4), 5))
    return _band_quantities(scn.band, float(scn.aod550), float(scn.alpha),
                            float(scn.pwv_cm), float(b["h_aer_km"]),
                            float(b["t0_c"]), float(b["p0_hpa"]), r,
                            float(tgt.z_m), float(scn.sensor.platform_h_m),
                            float(scn.target_temp_c + 273.15),
                            float(scn.bg_temp_c + 273.15),
                            float(eps_t), eps_b)


# --------------------------------------------------------------------------- #
# 光谱状态（供图件/诊断使用；缓存条数很小，避免内存膨胀）
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1024)
def _spectral_cached(band: str, aod550: float, alpha: float, pwv_cm: float,
                     t0_c: float, p0_hpa: float, r_ground_km: float,
                     z_target_m: float, z_sensor_m: float) -> dict:
    atmo = atmosphere.Atmo(aod550=aod550, alpha=alpha, pwv_cm=pwv_cm,
                           t0_c=t0_c, p0_hpa=p0_hpa)
    st = atmosphere.spectral_state(atmo, band, r_ground_km, z_target_m, z_sensor_m)
    # 只保留常用字段，丢开 tau_comp 以防内存膨胀
    keys = ("lam_um", "tau_lam", "l_path_lam", "tau_band", "l_path",
            "lam_eff", "r_slant_km", "r_ground_km")
    return {k: st[k] for k in keys if k in st}


def spectral_for(scn: Scenario, r_ground_km: float) -> dict:
    r = float(round(max(r_ground_km, 1e-4), 4))
    return _spectral_cached(scn.band, float(scn.aod550), float(scn.alpha),
                            float(scn.pwv_cm), float(params.ATMOS_BASE["t0_c"]),
                            float(params.ATMOS_BASE["p0_hpa"]), r,
                            float(scn.target.z_m), float(scn.sensor.platform_h_m))


# --------------------------------------------------------------------------- #
# 正向评估
# --------------------------------------------------------------------------- #
def evaluate(scn: Scenario, r_ground_km: float) -> dict:
    """单点评估，返回链路全部中间量。"""
    (l_t, l_b, s_t, s_b, l_path, t_app_t, t_app_b, d_t_app,
     lam_eff, tau_band, r_slant, _r_ground) = band_quantities(scn, r_ground_km)
    tgt = scn.target
    eps_t = tgt.eps if scn.eps_t is None else float(scn.eps_t)

    r_slant = max(float(r_slant), 1e-6)
    r0 = sensor_mod.fried_r0(lam_eff, scn.cn2, r_slant * 1000.0)
    s = scn.sensor
    fmax = s.f_max(d_t_app, lam_eff, r0)

    theta_mrad = tgt.d_eff_m / r_slant
    n_cyc = fmax * theta_mrad
    n50 = probability.n50_set(scn.n50_set)
    p_det = float(probability.p_task(n_cyc, n50["detect"]))
    p_rec = float(probability.p_task(n_cyc, n50["recognize"]))
    p_idf = float(probability.p_task(n_cyc, n50["identify"]))

    return dict(
        r_ground_km=float(r_ground_km), r_slant_km=float(r_slant),
        band=scn.band, target=scn.target_key, target_name=tgt.name, kind=tgt.kind,
        size_rule=scn.size_rule, d_eff_m=tgt.d_eff_m,
        target_temp_c=scn.target_temp_c, bg_temp_c=scn.bg_temp_c,
        dT_intrinsic_K=scn.dT_intrinsic_K,
        aod550=scn.aod550, alpha=scn.alpha, pwv_cm=scn.pwv_cm, cn2=scn.cn2,
        eps_t=float(eps_t), eps_b=float(params.BACKGROUND["eps"]),
        tau_band=float(tau_band), l_path=float(l_path), lam_eff=float(lam_eff),
        L_target=float(l_t), L_bg=float(l_b),
        t_app_t_K=float(t_app_t), t_app_b_K=float(t_app_b),
        dT_app_K=float(d_t_app),
        r0_m=float(r0) if np.isfinite(r0) else float("inf"),
        f_max=float(fmax), theta_mrad=float(theta_mrad), n_cycles=float(n_cyc),
        N50_set=scn.n50_set, N50_rec=n50["recognize"],
        P_detect=p_det, P_rec=p_rec, P_ident=p_idf,
        D_m=s.D_m, netd_k=s.netd_k, f_nyq=s.f_nyq_cyc_mrad, ifov_mrad=s.ifov_mrad,
    )


LONG_FIELDS = list(evaluate(Scenario(), 5.0).keys())


def evaluate_many(scn: Scenario, r_grid: Iterable[float]) -> List[dict]:
    return [evaluate(scn, r) for r in r_grid]


def scene_grid(scenarios: Iterable[Scenario], r_grid: Iterable[float]) -> List[dict]:
    out = []
    for i, scn in enumerate(scenarios):
        for row in evaluate_many(scn, r_grid):
            row["scenario_idx"] = i
            out.append(row)
    return out


# --------------------------------------------------------------------------- #
# 基线工况
# --------------------------------------------------------------------------- #
def baseline_scenario(band: str = "MWIR", target_key: str = "F16",
                      size_rule: str = "sqrt_area", n50_set: str = "NVESD",
                      preset: str = "RECOG") -> Scenario:
    b = params.BASELINE
    return Scenario(
        target_key=target_key,
        target_temp_c=b["target_temp_c"], bg_temp_c=b["bg_temp_c"],
        aod550=b["aod550"], alpha=b["alpha"], pwv_cm=b["pwv_cm"], cn2=b["cn2"],
        size_rule=size_rule, n50_set=n50_set,
        sensor=sensor_mod.make_sensor(band, preset=preset),
    )

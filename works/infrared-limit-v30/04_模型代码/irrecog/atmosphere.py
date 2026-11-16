# -*- coding: utf-8 -*-
"""
irrecog.atmosphere —— 光谱大气：斜程分层透过率与路径辐射（唯一实现）

物理模型
--------
沿"传感器—目标"直线（球面地球下的弦）切成 ``n_layers`` 个等长层，逐层取层中点
的大气状态，累加光学厚度：

    dτ(λ,i) = [β_aer(λ,h_i) + β_mol(λ,h_i)]·Δs + Σ_g k_g(λ,T_i,p_i)·N_g(h_i)·Δs
    τ(λ)    = Σ_i dτ(λ,i),   T(λ) = exp[−τ(λ)]
    L_path(λ) = Σ_i B(λ,T_i)·[exp(−τ_before,i) − exp(−τ_after,i)]

各分量
------
* 温度/气压廓线（ISO 2533:1975 分层）：
    0 ≤ h < h_trop（标准大气 11 km）：T = T0 − Γ·h，
        p = p0·(T/T0)^{gM/(RΓ)}，Γ = 6.5 K/km，指数 gM/(RΓ) = 5.25588；
    h_trop ≤ h ≤ 20 km：等温 216.65 K，p = p_trop·exp[−gM(h−h_trop)/(R·216.65)]。
  T0、p0 取地面值（Atmo.t0_c / p0_hpa）。
* 水汽：指数廓线，标高 H_wv=2 km，按可降水量 PWV 归一：
    ρ_v(h) = PWV_cm·10/(H_wv·1000)·exp(−h/H_wv)   [kg/m³]，∫ρ_v dh = PWV_cm·10 kg/m²。
* 气溶胶：外消光（Ångström 幂律，不含散射相函数与多次散射）：
    β_aer(λ,h) = (AOD550/H_aer)·exp(−h/H_aer)·(0.55/λ)^α   [km⁻¹]。
* 分子 Rayleigh 散射（口径修正）：
    τ_R,vert(λ) = 0.008735·λ^{-4.08}（550 nm 垂直光学厚度），H_R = 8 km，
    dτ_R = τ_R,vert·(n(h)/n0)·ds/H_R，n ∝ p/T。
* 气体吸收：HITRAN2020 逐线 Voigt 截面（cm²/molecule），按层温度与层气压
  双线性插值：
    - 温度节点 220/250/280/300 K（覆盖 0–12 km 的 216–288 K），
    - 气压节点 1.0/0.6/0.36/0.2 atm（覆盖地面到 12 km 的 1.0→0.19 atm）；
    - 缺气压节点的弱吸收物种（O₃/N₂O/CO）按 1 atm 截面使用（贡献 <1%，报告中说明）。
  截面文件 ``07_光谱数据/xsect_mwir.npz`` / ``xsect_lwir.npz``。
* 路径辐射：逐层 Planck，按累计光学厚度加权（不做逐层饱和求和）。

性能设计
--------
* 光谱网格、对比度权重、Planck 因子 c1/λ⁵、c2/λ、Rayleigh 垂直光学厚度按波段缓存；
* 层数组统一采用 (Nλ, 层) 的 C 连续布局：cumsum/exp/乘加全部连续访存，
  比 (层, Nλ) 布局快约 3 倍；
* 逐层光学厚度写成两次 BLAS 矩阵乘：把 (层×温度×气压) 权重矩阵与
  (温度×气压×Nλ) 截面矩阵相乘，避免 Python 循环；
* 分物种透过率仅在需要时计算（``with_components=False`` 时跳过，链路评估用）。
单点（0.05 cm⁻¹、40 层、MWIR 1.24 万点）目标 ≤15 ms。

单位约定：波长 μm、波数 cm⁻¹、柱数密度 molecules/cm²、截面 cm²/molecule、
辐亮度 W/(m²·sr·μm)、波段量 W/(m²·sr)。
"""

import os
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import params, radiometry

# --------------------------------------------------------------------------- #
# 常量与波段定义
# --------------------------------------------------------------------------- #
BANDS = {k: (v["lo_um"], v["hi_um"]) for k, v in params.BANDS.items()}

_SPEC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "07_光谱数据")
_SPECIES = ("H2O", "CO2", "CH4", "O3", "N2O", "CO")
_DRY_SPECIES = ("CO2", "CH4", "O3", "N2O", "CO")   # 共享干空气柱密度
_TAU_COMP_KEYS = ("H2O", "CO2", "CH4", "O3", "N2O", "CO", "AER", "MOL")

_NA = 6.02214076e23      # 1/mol
_M_H2O = 0.01801528      # kg/mol
_K_B = 1.380649e-23      # J/K
_G0 = 9.80665            # m/s²
_M_AIR = 0.0289644       # kg/mol
_R_GAS = 8.314462618     # J/(mol·K)
_T_TROPOPAUSE = 216.65   # K，ISO 2533 对流层顶温度
_H_RAYLEIGH_KM = 8.0     # Rayleigh 散射标高 km（6S 口径）
_TAU_R_COEF = 0.008735   # 550 nm 垂直光学厚度系数（λ 以 μm 计）
_TAU_R_EXP = 4.08
# Planck 常数：B(λ,T) = C1/λ⁵ / (e^{C2/(λT)}−1)，λ 用 μm，W/(m²·sr·μm)
_C1 = 2.0 * params.H_PLANCK * params.C_LIGHT ** 2 * 1e24
_C2 = params.H_PLANCK * params.C_LIGHT / params.K_BOLTZ * 1e6
_P_EXPONENT = _G0 * _M_AIR / (_R_GAS * 6.5)                      # 5.25588
_H_PRESSURE_KM = _R_GAS * _T_TROPOPAUSE / (_G0 * _M_AIR) / 1000.0  # 6.3416 km
_MIX_FIELD = {"CO2": "co2_ppm", "CH4": "ch4_ppb", "O3": "o3_ppb",
              "N2O": "n2o_ppb", "CO": "co_ppb"}
_MIX_SCALE = {"CO2": 1e-6, "CH4": 1e-9, "O3": 1e-9, "N2O": 1e-9, "CO": 1e-9}


# --------------------------------------------------------------------------- #
# 大气状态（唯一参数入口）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Atmo:
    """一个大气工况（地面气象 + 气溶胶 + 水汽 + 微量气体混合比）。"""
    aod550: float = 0.587          # 550 nm 气溶胶光学厚度
    alpha: float = 1.30            # Ångström 指数
    pwv_cm: float = 1.28           # 可降水量 cm（= 10 kg/m² 液态水当量）
    h_aer_km: float = 1.5          # 气溶胶标高 km
    t0_c: float = 15.0             # 地面温度 ℃
    p0_hpa: float = 1013.0         # 地面气压 hPa
    co2_ppm: float = 420.0
    o3_ppb: float = 35.0
    n2o_ppb: float = 332.0
    ch4_ppb: float = 1930.0
    co_ppb: float = 100.0
    cn2: float = 1e-15             # 湍流结构常数（大气本身不用，随工况携带）
    h_wv_km: float = 2.0           # 水汽标高 km
    lapse_k_per_km: float = 6.5    # 对流层温度直减率 K/km
    p_scale_km: float = 8.0        # 保留字段：不再用于主廓线（仅向后兼容）

    def with_(self, **kw) -> "Atmo":
        return replace(self, **kw)


# --------------------------------------------------------------------------- #
# 光谱网格与波段缓存
# --------------------------------------------------------------------------- #
def band_grid(band: str, step_cm: float = None) -> np.ndarray:
    """波段光谱网格：**波数域均匀**（Δν = step_cm），返回升序波长 (μm)。

    在波数域取点是因为 HITRAN 线宽本身以 cm⁻¹ 定义（1 atm 下 0.05–0.1 cm⁻¹），
    波长域均匀取点会在长波端严重欠采样、漏掉整条吸收线。
    """
    step = params.SPECTRAL_STEP_CM if step_cm is None else float(step_cm)
    lo_um, hi_um = BANDS[band]
    nu = np.arange(1e4 / hi_um, 1e4 / lo_um + 0.5 * step, step)
    return (1e4 / nu)[::-1].copy()          # λ 升序


class _BandCache:
    """一个（波段, 步长）的光谱网格与只算一次的常数。"""

    __slots__ = ("band", "step", "lam", "nu", "w", "w_dot_lam", "pl_A", "pl_E",
                 "tau_r_vert", "n_lam", "aod_shape")

    def __init__(self, band: str, step: float):
        self.band = band
        self.step = step
        self.lam = band_grid(band, step)
        self.nu = 1e4 / self.lam                          # cm⁻¹，降序
        self.n_lam = self.lam.size
        # 对比度权重 w(λ) ∝ dB/dT(λ,T_ref)·Δλ（参考温度取背景温度 293.15 K）
        self.w = np.asarray(radiometry.band_weights(self.lam), dtype=float)
        self.w_dot_lam = float(np.dot(self.w, self.lam))
        self.pl_A = _C1 / self.lam ** 5                   # Planck 的 c1/λ⁵
        self.pl_E = _C2 / self.lam                        # Planck 的 c2/λ
        self.tau_r_vert = _TAU_R_COEF * self.lam ** (-_TAU_R_EXP)
        self.aod_shape: Dict[float, np.ndarray] = {}

    def aer_shape(self, alpha: float) -> np.ndarray:
        key = round(float(alpha), 6)
        arr = self.aod_shape.get(key)
        if arr is None:
            arr = (0.55 / self.lam) ** float(alpha)
            self.aod_shape[key] = arr
        return arr


@lru_cache(maxsize=16)
def _band_cache(band: str, step_cm: float) -> _BandCache:
    return _BandCache(band, step_cm)


# --------------------------------------------------------------------------- #
# HITRAN 截面缓存（支持多温度 × 多气压）
# --------------------------------------------------------------------------- #
_KEY_RE = re.compile(r"^([A-Za-z0-9]+)_T(\d+)(?:_P([0-9.]+))?$")


class _XsectCache:
    """一个（波段, 步长）的 HITRAN 截面缓存。

    键格式：``<物种>_T<温度>_P<气压两位小数>``（气压为 1 atm 时 P 可省略）。
    每个物种存为 (nT, nP, Nλ) 数组，已插值到波段网格。
    """

    __slots__ = ("temps", "species", "pressures", "missing", "source", "nu_src")

    def __init__(self, band: str, step: float, band_cache: _BandCache):
        path = os.path.join(_SPEC_DIR, "xsect_%s.npz" % band.lower())
        if not os.path.exists(path):
            raise FileNotFoundError(
                "缺少 %s 波段吸收截面 %s，请先运行 00_构建脚本/build_xsect.py"
                % (band, path))
        d = np.load(path, allow_pickle=False)
        nu_src = np.asarray(d["nu"], dtype=float)
        nu_q = band_cache.nu
        files = set(d.files)

        # 解析键 → {species: {T: {P: array}}}
        raw: Dict[str, Dict[float, Dict[float, np.ndarray]]] = {}
        for k in files:
            m = _KEY_RE.match(k)
            if not m:
                continue
            sp, T, P = m.group(1), m.group(2), m.group(3)
            if sp not in _SPECIES:
                continue
            raw.setdefault(sp, {}).setdefault(float(T), {})[float(P) if P else 1.0] = d[k]

        if not raw:
            raise ValueError("%s 中未找到任何 <物种>_T<温度>[ _P<气压>] 截面键" % path)

        self.temps = np.array(sorted({T for byT in raw.values() for T in byT}), dtype=float)
        self.species: Dict[str, np.ndarray] = {}
        self.pressures: Dict[str, np.ndarray] = {}
        self.missing: List[str] = []
        n_lam = band_cache.n_lam
        for sp in _SPECIES:
            byT = raw.get(sp)
            if not byT:
                self.missing.append(sp)
                continue
            # 缺失温度节点用最近温度补（不同物种温度集可能略有差异）
            avail_T = np.array(sorted(byT), dtype=float)
            presses = np.array(sorted({P for byP in byT.values() for P in byP}), dtype=float)
            stack = np.empty((self.temps.size, presses.size, n_lam), dtype=float)
            for i, T in enumerate(self.temps):
                Tuse = T if T in byT else float(avail_T[np.argmin(np.abs(avail_T - T))])
                byP = byT[Tuse]
                avail_P = np.array(sorted(byP), dtype=float)
                for j, P in enumerate(presses):
                    Puse = P if P in byP else float(avail_P[np.argmin(np.abs(avail_P - P))])
                    stack[i, j, :] = np.interp(
                        nu_q, nu_src, np.nan_to_num(np.asarray(byP[Puse], dtype=float),
                                                    nan=0.0, posinf=0.0, neginf=0.0),
                        left=0.0, right=0.0)
            stack = np.clip(stack, 0.0, None).astype(np.float32)
            self.species[sp] = stack
            self.pressures[sp] = presses

        self.nu_src = nu_src if "nu" in files else None
        self.source = "%s（HITRAN2020 逐线 Voigt，T=%s K，p=%s atm）" % (
            path, "/".join("%d" % int(t) for t in self.temps),
            "/".join("%g" % p for p in np.unique(np.concatenate(
                [self.pressures[s] for s in self.species]))))
        if self.missing:
            self.source += "；缺失物种=%s" % ",".join(self.missing)


@lru_cache(maxsize=8)
def _xsect_cache(band: str, step_cm: float) -> _XsectCache:
    return _XsectCache(band, step_cm, _band_cache(band, step_cm))


@lru_cache(maxsize=64)
def _dry_groups(band: str, step_cm: float, co2_ppm: float, ch4_ppb: float,
                o3_ppb: float, n2o_ppb: float, co_ppb: float):
    """把干气体按气压节点分组并合并为等效截面。

    返回 tuple[(pressures(nP,), σ_eff(nT,nP,Nλ), [(species, mix), ...]), ...]
    """
    xs = _xsect_cache(band, step_cm)
    mixes = {"CO2": co2_ppm, "CH4": ch4_ppb, "O3": o3_ppb,
             "N2O": n2o_ppb, "CO": co_ppb}
    groups: Dict[Tuple[float, ...], List[Tuple[str, float]]] = {}
    for sp in _DRY_SPECIES:
        mix = float(mixes[sp]) * _MIX_SCALE[sp]
        if sp not in xs.species or mix <= 0.0:
            continue
        groups.setdefault(tuple(float(p) for p in xs.pressures[sp]), []).append((sp, mix))
    out = []
    for pkey, items in groups.items():
        sig = None
        for sp, mix in items:
            g = xs.species[sp] * mix
            sig = g if sig is None else sig + g
        out.append((np.asarray(pkey, dtype=float), sig, items))
    return tuple(out)


# --------------------------------------------------------------------------- #
# 廓线与几何
# --------------------------------------------------------------------------- #
def _profile_tp(atmo: Atmo, h_km: np.ndarray):
    """ISO 2533 分层的温度 [K] 与气压 [hPa]（h 为层中点高度 km）。"""
    T0 = float(atmo.t0_c) + 273.15
    lapse = max(float(atmo.lapse_k_per_km), 1e-6)
    h_trop = (T0 - _T_TROPOPAUSE) / lapse            # 标准参数下 = 11.0 km
    h_trop = min(max(h_trop, 5.0), 20.0)
    h = np.maximum(h_km, 0.0)

    T = np.where(h < h_trop, T0 - lapse * h, _T_TROPOPAUSE)
    expo = _G0 * _M_AIR / (_R_GAS * lapse)           # = 5.25588（Γ=6.5 时）
    p_trop = float(atmo.p0_hpa) * (_T_TROPOPAUSE / T0) ** expo
    p = np.where(h < h_trop,
                 float(atmo.p0_hpa) * (T / T0) ** expo,
                 p_trop * np.exp(-(h - h_trop) / _H_PRESSURE_KM))
    return T, p


def _geometry(r_ground_km: float, z_target_m: float, z_sensor_m: float,
              n_layers: int) -> dict:
    """球面地球弦几何：返回层中点高度、层长、斜距。

    2D 平面：地心在原点，传感器位于 (0, R+z_s)，目标位于
    (R+z_t)·(sin φ, cos φ)，φ = r_ground/R_E 为地心角；视线为两点连线（弦），
    按等弦长切层，层高取层中点 |P|−R_E。
    """
    R = params.R_EARTH_KM
    rs = R + float(z_sensor_m) / 1000.0
    rt = R + float(z_target_m) / 1000.0
    phi = max(float(r_ground_km), 0.0) / R
    p_s = np.array([0.0, rs])
    p_t = np.array([rt * np.sin(phi), rt * np.cos(phi)])
    vec = p_t - p_s
    chord = float(np.hypot(vec[0], vec[1]))
    chord_safe = max(chord, 1e-9)
    u = vec / chord_safe
    t = (np.arange(n_layers, dtype=float) + 0.5) * (chord_safe / n_layers)
    p_mid = p_s[None, :] + t[:, None] * u[None, :]
    h_km = np.hypot(p_mid[:, 0], p_mid[:, 1]) - R        # 层中点海拔 km
    return dict(h_km=h_km, ds_km=chord_safe / n_layers, r_slant_km=chord)


def _interp_weights(values: np.ndarray, nodes: np.ndarray) -> np.ndarray:
    """把一组连续值映射到节点上的线性插值权重矩阵 (n_values, n_nodes)，端点箝位。"""
    n = values.size
    if nodes.size == 1:
        return np.ones((n, 1))
    j = np.clip(np.searchsorted(nodes, values) - 1, 0, nodes.size - 2)
    denom = np.maximum(nodes[j + 1] - nodes[j], 1e-12)
    f = np.clip((values - nodes[j]) / denom, 0.0, 1.0)
    W = np.zeros((n, nodes.size))
    idx = np.arange(n)
    W[idx, j] += 1.0 - f
    W[idx, j + 1] += f
    return W


def _layer_dtau(col: np.ndarray, WT: np.ndarray, sig: np.ndarray,
                pressures: np.ndarray, p_atm: np.ndarray) -> np.ndarray:
    """单组气体的逐层光学厚度 (n_layers, Nλ)。

    col : (n_layers,) 该组气体的层柱数密度
    WT  : (n_layers, nT) 温度插值权重
    sig : (nT, nP, Nλ) 截面
    """
    n_layers = col.size
    nT, nP, n_lam = sig.shape
    if nP == 1:
        WP = np.ones((n_layers, 1))
    else:
        logp = np.log(np.maximum(p_atm, 1e-8))
        logn = np.log(np.maximum(pressures, 1e-8))
        j = np.clip(np.searchsorted(logn, logp) - 1, 0, nP - 2)
        f = np.clip((logp - logn[j]) / np.maximum(logn[j + 1] - logn[j], 1e-12), 0.0, 1.0)
        WP = np.zeros((n_layers, nP))
        idx = np.arange(n_layers)
        WP[idx, j] += 1.0 - f
        WP[idx, j + 1] += f
    # (n_layers, nT, nP) 权重矩阵 → BLAS： (n_layers, nT*nP) @ (nT*nP, Nλ)
    # 截面以 float32 存储，BLAS sgemm 相对 dgemm 约快 1.6–2 倍、内存减半；
    # 透过率仅用于波段积分，float32 相对精度 1e-7 足够。
    C = (col[:, None, None] * WT[:, :, None] * WP[:, None, :]).astype(np.float32)
    return (C.reshape(n_layers, nT * nP) @ sig.reshape(nT * nP, n_lam)).astype(np.float32)


# --------------------------------------------------------------------------- #
# 主接口：单点光谱状态
# --------------------------------------------------------------------------- #
def spectral_state(atmo: Atmo, band: str, r_ground_km: float,
                   z_target_m: float = 0.0, z_sensor_m: float = 8000.0,
                   n_layers: int = None, with_components: bool = True) -> dict:
    """斜程光谱状态：透过率谱、路径辐亮度谱与波段量。

    返回 dict：
        lam_um        (Nλ,) 波长 μm 升序
        tau_lam       (Nλ,) 总透过率
        l_path_lam    (Nλ,) 路径辐亮度 W/(m²·sr·μm)
        tau_band      波段对比度加权平均透过率
        l_path        波段平均路径辐亮度 W/(m²·sr)
        tau_comp      {H2O,CO2,CH4,O3,N2O,CO,AER,MOL: (Nλ,) 各自透过率}（with_components=True）
        lam_eff       波段加权中心波长 μm
        r_slant_km    弦长（斜距）km
        r_ground_km   地面距离 km
        n_layers      层数
        source        截面数据来源说明
    """
    n_layers = int(params.N_LAYERS if n_layers is None else n_layers)
    bc = _band_cache(band, params.SPECTRAL_STEP_CM)
    lam, w, n_lam = bc.lam, bc.w, bc.n_lam

    # ---------------- 几何与大气廓线 ----------------
    geo = _geometry(max(float(r_ground_km), 0.0), z_target_m, z_sensor_m, n_layers)
    h_km = geo["h_km"]
    ds_km = geo["ds_km"]
    ds_cm = ds_km * 1e5

    T_lay, p_lay = _profile_tp(atmo, h_km)
    p_atm = p_lay / 1013.25
    T0 = float(atmo.t0_c) + 273.15

    # 干空气柱数密度 [molecules/cm²]（p[Pa]/(k·T) → cm⁻³，再乘 ds[cm]）
    n_air_cm3 = (p_lay * 100.0) / (_K_B * T_lay) * 1e-6
    col_air = n_air_cm3 * ds_cm

    # 水汽：指数标高、PWV 归一 → 层柱数密度 [molecules/cm²]
    rho_v = (float(atmo.pwv_cm) * 10.0 / (float(atmo.h_wv_km) * 1000.0)
             * np.exp(-np.maximum(h_km, 0.0) / float(atmo.h_wv_km)))       # kg/m³
    col_h2o = rho_v / _M_H2O * _NA * 1e-6 * ds_cm

    # 气溶胶与 Rayleigh
    beta_aer550 = (float(atmo.aod550) / max(float(atmo.h_aer_km), 1e-6)
                   * np.exp(-np.maximum(h_km, 0.0) / max(float(atmo.h_aer_km), 1e-6)))
    beta_aer550_ds = beta_aer550 * ds_km
    aer_shape = bc.aer_shape(float(atmo.alpha))
    tau_aer = float(beta_aer550_ds.sum()) * aer_shape
    mol_col = float(np.sum((p_lay / float(atmo.p0_hpa)) * (T0 / T_lay)
                           * (ds_km / _H_RAYLEIGH_KM)))
    tau_mol = bc.tau_r_vert * mol_col

    # ---------------- 截面与逐层光学厚度（层数组用 (Nλ, 层) 连续布局）----
    xs = _xsect_cache(band, params.SPECTRAL_STEP_CM)
    WT = _interp_weights(T_lay, xs.temps)                 # (n_layers, nT)

    dtau_t = np.zeros((n_lam, n_layers), dtype=np.float32)   # transpose 布局

    # 水汽
    tau_h2o_l = None
    if "H2O" in xs.species:
        tau_h2o_l = _layer_dtau(col_h2o, WT, xs.species["H2O"],
                                xs.pressures["H2O"], p_atm)
        dtau_t += tau_h2o_l.T

    # 干气体（按气压节点分组，等效截面合并）
    dry_tau_spectral: Dict[str, np.ndarray] = {}
    dry_groups = _dry_groups(band, params.SPECTRAL_STEP_CM,
                             float(atmo.co2_ppm), float(atmo.ch4_ppb),
                             float(atmo.o3_ppb), float(atmo.n2o_ppb),
                             float(atmo.co_ppb))
    for pressures, sig_eff, items in dry_groups:
        tau_l = _layer_dtau(col_air, WT, sig_eff, pressures, p_atm)
        dtau_t += tau_l.T
        if with_components:
            # 各组内按混合比拆分（线性可加）
            for sp, mix in items:
                sig_sp = xs.species[sp]
                tau_sp_l = _layer_dtau(col_air * mix, WT, sig_sp,
                                       xs.pressures[sp], p_atm)
                dry_tau_spectral[sp] = tau_sp_l.sum(axis=0)

    # 气溶胶 + 分子散射的逐层光学厚度（(Nλ, 层) 布局）
    dtau_t += (beta_aer550_ds[:, None] * aer_shape[None, :]).T
    mol_factor = (p_lay / float(atmo.p0_hpa)) * (T0 / T_lay) * ds_km / _H_RAYLEIGH_KM
    dtau_t += np.outer(bc.tau_r_vert, mol_factor)

    # ---------------- 累计光学厚度 → 透过率与路径辐射 ----------------
    cum = np.cumsum(dtau_t, axis=1)                        # (Nλ, n_layers)，float32
    trans = np.exp(-cum, out=cum)
    tau_lam = trans[:, -1].astype(np.float64)

    dE = np.empty_like(trans)
    dE[:, 0] = 1.0 - trans[:, 0]
    np.subtract(trans[:, :-1], trans[:, 1:], out=dE[:, 1:])
    B = (bc.pl_A[:, None] / np.expm1(bc.pl_E[:, None] / T_lay[None, :])).astype(np.float32)
    L_path_lam = np.einsum("nl,nl->n", B, dE).astype(np.float64)

    # ---------------- 波段标量 ----------------
    tau_band = float(np.dot(w, tau_lam))
    l_path = float(np.dot(w, L_path_lam))

    # ---------------- 分物种透过率 ----------------
    tau_comp = {}
    if with_components:
        if tau_h2o_l is not None:
            tau_comp["H2O"] = np.exp(-tau_h2o_l.sum(axis=0))
        for sp in _DRY_SPECIES:
            if sp in dry_tau_spectral:
                tau_comp[sp] = np.exp(-dry_tau_spectral[sp])
        for sp in _SPECIES:
            if sp not in tau_comp:
                tau_comp[sp] = np.ones(n_lam)
        tau_comp["AER"] = np.exp(-tau_aer)
        tau_comp["MOL"] = np.exp(-tau_mol)

    return dict(
        lam_um=lam, tau_lam=tau_lam, l_path_lam=L_path_lam,
        tau_band=tau_band, l_path=l_path,
        tau_comp=tau_comp,
        lam_eff=bc.w_dot_lam,
        r_slant_km=float(geo["r_slant_km"]),
        r_ground_km=float(max(r_ground_km, 0.0)),
        n_layers=n_layers,
        source=xs.source,
        modtran_equiv_vis_km=float(3.912 / max(
            float(atmo.aod550) / max(float(atmo.h_aer_km), 1e-9), 1e-9)),
    )


# --------------------------------------------------------------------------- #
# 基准与自检
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import time

    a = Atmo()
    print("波段网格：", {b: "%d 点 (%.3f–%.3f μm)" % (
        band_grid(b).size, band_grid(b)[0], band_grid(b)[-1]) for b in BANDS})
    for band in ("MWIR", "LWIR"):
        spectral_state(a, band, 20.0, 0.0, 8000.0)      # 预热
        t0 = time.perf_counter()
        n = 20
        for _ in range(n):
            st = spectral_state(a, band, 20.0, 0.0, 8000.0)
        dt = (time.perf_counter() - t0) / n * 1e3
        prod = np.ones_like(st["tau_lam"])
        for v in st["tau_comp"].values():
            prod = prod * v
        print("%s: 单点 %.2f ms | tau_band=%.4f | l_path=%.5f | lam_eff=%.3f μm | "
              "r_slant=%.3f km | Πτ_comp−τ_lam max|Δ|=%.2e"
              % (band, dt, st["tau_band"], st["l_path"], st["lam_eff"],
                 st["r_slant_km"], np.max(np.abs(prod - st["tau_lam"]))))
        print("   source:", st["source"].split("（")[0], " 层数", st["n_layers"])

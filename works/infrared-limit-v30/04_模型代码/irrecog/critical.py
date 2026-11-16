# -*- coding: utf-8 -*-
"""
irrecog.critical —— 临界状态反解（对数域二分求解器 + 解析天花板）

本模块落实《重制实施规范》§2 F11/F12：
- 临界距离全部改为**对数域包围 + 二分（Illinois 加速）细化**，相对精度
  |ΔlnR| < 1e-3，搜索区间 [0.2, 400] km；两端越界时返回 NaN + 截断原因，
  禁止把搜索边界当成解。
- 解析天花板：R_slant = f_upper(λ_eff)·D_eff/N50，λ_eff 取 atmosphere 返回的
  对比度加权等效波长，再按球面几何（弦长，含地球曲率、不含折射）换算地面距离。
- 热交叉盲区：在参考距离 r_ref 处先用 ΔT 细扫定位 P<阈值 的连续区间，再对两侧
  P=阈值 的根做二分（ΔT 在 0 附近不能取对数）。
- 临界 AOD/Cn²/口径/NETD：在单调假设下做对数域二分，相对容差 1e-3。

性能
----
最贵的一步是 ``atmosphere.spectral_state``。本模块所有评估都走
``chain.evaluate`` / ``chain.band_quantities``（波段标量缓存，内存极小，见
chain.py 的缓存策略）；对"固定距离、只变一个参数"的扫描（ΔT、ε、Cn²）另提供
:class:`BandState` 与 :func:`probabilities` 向量化快速通道：大气只算一份，
参数变化只重算 Planck/MTF/概率，与 ``chain.evaluate`` 逐点一致
（:func:`validate_fast_path` 做数值校核）。

对外接口（别名保持向后兼容）
----------------------------
- 距离：``range_for_p`` / ``range_summary`` / ``r50`` / ``p_curve``
- 解析：``analytic_resolution_range`` / ``contrast_floor_range``
- 热状态：``delta_t_for_p`` / ``dt_curve``
- 临界参数：``aod_for_p`` / ``cn2_for_p`` / ``aperture_for_p`` / ``netd_for_p`` /
  ``pixel_count_for_p``
"""

import math
from functools import lru_cache
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import chain, params, probability, radiometry, sensor as sensor_mod

TASK_TO_KEY = {"detect": "P_detect", "recognize": "P_rec", "identify": "P_ident"}
TASKS = ("detect", "recognize", "identify")
TASK_CN = {"detect": "探测", "recognize": "识别", "identify": "辨认"}

# --------------------------------------------------------------------------- #
# 搜索区间与精度（规范 F11/F12）
# --------------------------------------------------------------------------- #
R_LO_KM = 0.2         # 搜索下限（地面距离）
R_HI_KM = 400.0       # 搜索上限
REL_TOL_R = 1e-3      # |ΔlnR| 相对精度 → 距离相对精度 ≈ 0.1%
REL_TOL_X = 1e-3      # 临界参数（AOD/Cn²/口径/NETD）相对容差
DT_TOL_K = 1e-4       # 临界温差根容差（K）
N_SCAN = 14           # 无曲线数据时的共享粗扫描点数
MAX_ITER = 80

#: 默认距离采样（仅用于 p_curve 等可视化）
R_GRID = np.geomspace(R_LO_KM, R_HI_KM, 120)

#: 临界距离汇总的 5 个默认指标
LEVEL_SPECS = (
    ("R50_ground_km", "recognize", 0.5),
    ("R90_ground_km", "recognize", 0.9),
    ("R10_ground_km", "recognize", 0.1),
    ("Rdet50_ground_km", "detect", 0.5),
    ("Rident50_ground_km", "identify", 0.5),
)


# --------------------------------------------------------------------------- #
# 单点评估（全部走 chain，保持与正向模型严格一致）
# --------------------------------------------------------------------------- #
def _p(scn: chain.Scenario, r_km: float, task: str) -> float:
    """单点任务概率。"""
    return float(chain.evaluate(scn, r_km)[TASK_TO_KEY[task]])


def p_values(scn: chain.Scenario, r_km: float) -> Dict[str, float]:
    """一次评估取探测/识别/辨认三个概率。"""
    row = chain.evaluate(scn, r_km)
    return {task: float(row[TASK_TO_KEY[task]]) for task in TASKS}


def point(scn: chain.Scenario, r_km: float) -> Dict[str, object]:
    """单点链路诊断量（即 chain.evaluate 的完整返回，供汇总表取 R50 处的中间量）。"""
    return chain.evaluate(scn, r_km)


# --------------------------------------------------------------------------- #
# 一维括号求根（Illinois / regula falsi，坐标可选 log / linear）
# --------------------------------------------------------------------------- #
def _illinois(g: Callable[[float], float], lo: float, hi: float,
              g_lo: float, g_hi: float, coord: str = "log",
              rel_tol: float = REL_TOL_R, max_iter: int = MAX_ITER) -> Tuple[float, int]:
    """在 [lo, hi] 上求 g(x)=0，要求 g_lo>=0>g_hi 且 g 单调。

    ``coord="log"`` 在 ln x 坐标上度量区间宽度（即停止条件为 |Δlnx|<=rel_tol，
    对应参数相对精度）；``coord="linear"`` 用绝对容差 rel_tol（ΔT/K 等）。
    """
    if coord == "log":
        tf, inv = math.log, math.exp
    else:
        tf, inv = (lambda v: float(v)), (lambda v: float(v))
    a, b = tf(lo), tf(hi)
    fa, fb = float(g_lo), float(g_hi)
    side = 0
    n = 0
    for _ in range(max_iter):
        if (b - a) <= rel_tol:
            break
        if fb != fa:
            x = (a * fb - b * fa) / (fb - fa)
        else:
            x = 0.5 * (a + b)
        if not (a < x < b):                      # 数值安全：插值点必须严格落在括号内
            x = 0.5 * (a + b)
        fx = float(g(inv(x)))
        n += 1
        if fx >= 0.0:
            a, fa = x, fx
            if side == 1:
                fb *= 0.5
            side = 1
        else:
            b, fb = x, fx
            if side == -1:
                fa *= 0.5
            side = -1
    return float(inv(0.5 * (a + b))), n


# --------------------------------------------------------------------------- #
# 距离反解
# --------------------------------------------------------------------------- #
def scan_curve(scn: chain.Scenario,
               n_scan: int = N_SCAN) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """在 [R_LO, R_HI] 对数等距粗扫描，返回 (rs, {task: P 数组})（共享一次正向评估）。"""
    rs = np.geomspace(R_LO_KM, R_HI_KM, int(n_scan))
    ps = {task: np.empty(rs.size) for task in TASKS}
    for i, r in enumerate(rs):
        row = chain.evaluate(scn, float(r))
        for task in TASKS:
            ps[task][i] = float(row[TASK_TO_KEY[task]])
    return rs, ps


def solve_from_curve(scn: chain.Scenario, task: str, p_target: float,
                     rs: Sequence[float], ps: Sequence[float]) -> Dict[str, object]:
    """由已评估的 P(r) 曲线（单调不增）反解 P=p_target 的地面距离。

    返回 dict(r_km, censored, p_lo, p_hi, n_iter)；截断时 r_km=NaN 并给出原因。
    """
    rs = np.asarray(rs, dtype=float)
    ps = np.asarray(ps, dtype=float)
    order = np.argsort(rs)
    rs, ps = rs[order], ps[order]
    p_lo, p_hi = float(ps[0]), float(ps[-1])
    if ps[0] < p_target:
        return dict(r_km=float("nan"),
                    censored=f"近距离即不满足（P({rs[0]:.4g} km)={ps[0]:.3f}<{p_target:g}）",
                    p_lo=p_lo, p_hi=p_hi, n_iter=0)
    if ps[-1] >= p_target:
        return dict(r_km=float("nan"),
                    censored=f"超出搜索上限（P({rs[-1]:.4g} km)={ps[-1]:.3f}≥{p_target:g}）",
                    p_lo=p_lo, p_hi=p_hi, n_iter=0)
    idx = None
    for i in range(1, rs.size):
        if ps[i - 1] >= p_target > ps[i]:
            idx = i
            break
    if idx is None:                      # 数值上不应发生
        return dict(r_km=float("nan"), censored="未找到根", p_lo=p_lo, p_hi=p_hi, n_iter=0)
    r_root, n = _illinois(lambda r: _p(scn, r, task) - p_target,
                          float(rs[idx - 1]), float(rs[idx]),
                          float(ps[idx - 1] - p_target), float(ps[idx] - p_target),
                          coord="log", rel_tol=REL_TOL_R)
    return dict(r_km=float(r_root), censored="", p_lo=p_lo, p_hi=p_hi, n_iter=int(n))


def range_for_p(scn: chain.Scenario, task: str = "recognize", p_target: float = 0.5,
                r_grid: Optional[np.ndarray] = None) -> Dict[str, object]:
    """临界距离（地面 km）：P=p_target 的根，对数域二分至相对精度 1e-3。

    参数 ``r_grid`` 仅为向后兼容保留（新求解器不再依赖固定距离网格）。
    返回 dict(r_km, censored, p_lo, p_hi, n_iter)；截断时 r_km=NaN。
    """
    rs, ps = scan_curve(scn, N_SCAN)
    return solve_from_curve(scn, task, p_target, rs, ps[task])


def r50(scn: chain.Scenario, task: str = "recognize",
        r_grid: Optional[np.ndarray] = None) -> float:
    """识别临界距离 R50（地面 km）；截断返回 NaN。"""
    return float(range_for_p(scn, task, 0.5)["r_km"])


def range_summary(scn: chain.Scenario,
                  rows: Optional[Iterable[dict]] = None,
                  specs: Sequence[Tuple[str, str, float]] = LEVEL_SPECS) -> Dict[str, Dict[str, object]]:
    """一次求解 5 个临界距离指标（R50/R90/R10/Rdet50/Rident50）。

    ``rows`` 若给出（长表该工况的逐距离行），直接复用其 P(r) 曲线做包围，再对每个
    根做对数域二分细化——满足规范 F11 的求解器口径，同时避免重复计算大气。
    """
    if rows is not None:
        rows = list(rows)
        rs = np.array([float(r["r_ground_km"]) for r in rows], dtype=float)
        ps = {task: np.array([float(r[TASK_TO_KEY[task]]) for r in rows], dtype=float)
              for task in TASKS}
    else:
        rs, ps = scan_curve(scn, N_SCAN)
    out: Dict[str, Dict[str, object]] = {}
    for name, task, level in specs:
        out[name] = solve_from_curve(scn, task, level, rs, ps[task])
    return out


# --------------------------------------------------------------------------- #
# 球面几何与解析天花板（规范 F5/F11）
# --------------------------------------------------------------------------- #
def spherical_ground_range(r_slant_km: float, z_sensor_km: float,
                           z_target_km: float, r_earth_km: float = None) -> float:
    """球面几何：由斜距（两点弦长）与两端高度求地面距离 r_g = R_E·φ。

    cosφ = [(R+zs)² + (R+zt)² − S²] / [2(R+zs)(R+zt)]
    """
    re = params.R_EARTH_KM if r_earth_km is None else float(r_earth_km)
    rs = re + float(z_sensor_km)
    rt = re + float(z_target_km)
    s = max(float(r_slant_km), 0.0)
    cos_phi = (rs ** 2 + rt ** 2 - s ** 2) / (2.0 * rs * rt)
    phi = math.acos(min(1.0, max(-1.0, cos_phi)))
    return float(re * phi)


def slant_from_ground(r_ground_km: float, z_sensor_km: float, z_target_km: float,
                      r_earth_km: float = None) -> float:
    """球面几何反算：地面距离 → 斜距（弦长）。"""
    re = params.R_EARTH_KM if r_earth_km is None else float(r_earth_km)
    rs = re + float(z_sensor_km)
    rt = re + float(z_target_km)
    phi = float(r_ground_km) / re
    return float(math.sqrt(rs ** 2 + rt ** 2 - 2.0 * rs * rt * math.cos(phi)))


def analytic_resolution_range(scn: chain.Scenario, task: str = "recognize") -> Dict[str, float]:
    """纯分辨率天花板：R_slant = f_upper(λ_eff)·D_eff/N50，再换算地面距离。

    λ_eff 取 atmosphere 返回的对比度加权等效波长（F2 权重）。该权重只与波段和
    背景温度有关、与距离无关，因此这里复用一次链路上的光谱状态（已缓存）。
    """
    s = scn.sensor
    tgt = scn.target
    row = chain.evaluate(scn, R_LO_KM)
    lam_eff = float(row["lam_eff"])
    f_up = float(s.f_upper(lam_eff))
    n50 = float(probability.n50_set(scn.n50_set)[task])
    r_slant = f_up * float(tgt.d_eff_m) / max(n50, 1e-12)
    z_t = float(tgt.z_m) / 1000.0
    z_s = float(s.platform_h_m) / 1000.0
    out = dict(r_slant_km=float(r_slant), r_ground_km=float("nan"),
               f_upper_cyc_mrad=f_up, N50=n50, d_eff_m=float(tgt.d_eff_m),
               lam_eff_um=lam_eff, z_target_km=z_t, z_sensor_km=z_s,
               r_earth_km=params.R_EARTH_KM, horizon_below=False, censored="")
    dz_km = abs(z_s - z_t)
    if r_slant <= dz_km + 1e-9:
        # 解析天花板的斜距小于平台-目标高度差：目标在几何地平线以下，没有地面交点
        out.update(censored="低于几何地平线（R_res 斜距小于平台-目标高度差）",
                   horizon_below=True)
        return out
    out["r_ground_km"] = spherical_ground_range(r_slant, z_s, z_t)
    return out


def contrast_floor_range(scn: chain.Scenario, task: str = "recognize",
                         n_scan: int = 24) -> Dict[str, object]:
    """对比度地板距离：|ΔT_app(r)| 降到 k·NETD/τ_opt 处的地面距离。

    超过该距离 f_max=0，任何分辨率都不起作用。用正向链路的真实 ΔT_app 求根，
    不再用 ΔT_intrinsic 的线性近似（规范 F12 的对比度地板口径）。
    """
    s = scn.sensor
    floor = float(s.delta_t_floor_k / max(s.tau_opt, 1e-9))
    rs = np.geomspace(R_LO_KM, R_HI_KM, max(8, int(n_scan)))
    dts = np.array([abs(float(chain.evaluate(scn, float(r))["dT_app_K"])) for r in rs])
    d0, d1 = float(dts[0]), float(dts[-1])
    if d0 <= floor:
        return dict(r_ground_km=float("nan"),
                    censored="近距离即低于对比度地板（热交叉或对比度不足）",
                    floor_K=float(floor))
    if d1 > floor:
        return dict(r_ground_km=float("nan"),
                    censored=f"超出搜索上限（P({R_HI_KM:g} km) 仍高于对比度地板）",
                    floor_K=float(floor))
    idx = None
    for i in range(1, rs.size):
        if dts[i - 1] > floor >= dts[i]:
            idx = i
            break
    if idx is None:
        return dict(r_ground_km=float("nan"), censored="未找到根", floor_K=float(floor))
    r_root, _ = _illinois(lambda r: abs(float(chain.evaluate(scn, r)["dT_app_K"])) - floor,
                          float(rs[idx - 1]), float(rs[idx]),
                          float(dts[idx - 1] - floor), float(dts[idx] - floor),
                          coord="log", rel_tol=REL_TOL_R)
    return dict(r_ground_km=float(r_root), censored="", floor_K=float(floor))


# --------------------------------------------------------------------------- #
# 向量化快速通道：固定距离处只变 ΔT / ε / Cn²
# --------------------------------------------------------------------------- #
def _fmax_vec(d_t_app, sensor, lam_eff: float, r0_m: float) -> np.ndarray:
    """``sensor.f_max`` 的向量化等价实现（批量 ΔT 扫描用，逐点严格一致）。"""
    d = np.atleast_1d(np.asarray(d_t_app, dtype=float))
    out = np.zeros(d.shape, dtype=float)
    if not np.all(np.isfinite(d)):
        d = np.nan_to_num(d, nan=0.0, posinf=0.0, neginf=0.0)
    f_hi = float(sensor.f_upper(lam_eff))
    if f_hi <= 0:
        return out
    n_grid = 600
    fg = np.linspace(0.0, f_hi, n_grid)
    mtf = np.asarray(sensor.mtf(fg, lam_eff, r0_m), dtype=float)
    d_eff = float(sensor.tau_opt) * np.abs(d)
    floor = float(sensor.delta_t_floor_k)
    req = np.full(d.shape, np.inf)
    mask = d_eff > floor
    req[mask] = float(sensor.k_mrtd) * float(sensor.netd_k) / d_eff[mask]
    if np.any(mask):
        # mtf 在 [0, f_hi] 上不增 → -mtf 不减，searchsorted 定位最后一个 mtf>=req 的网格点
        idx = np.searchsorted(-mtf, -req, side="right") - 1
        valid = mask & (idx >= 0)
        if np.any(valid):
            i = np.clip(idx[valid], 0, n_grid - 1)
            i1 = np.minimum(i + 1, n_grid - 1)
            f0, y0, y1 = fg[i], mtf[i], mtf[i1]
            denom = y1 - y0
            frac = np.where(np.abs(denom) > 1e-15,
                            (req[valid] - y0) / np.where(np.abs(denom) > 1e-15, denom, 1.0),
                            0.0)
            frac = np.clip(frac, 0.0, 1.0)
            fv = f0 + frac * (fg[i1] - f0)
            fv = np.where(i >= n_grid - 1, f_hi, fv)
            out[valid] = fv
    return out


class BandState:
    """固定距离处的波段光谱状态 + 视在温度反演器（供 ΔT/ε 变体批量扫描）。

    光谱大气只算一份（``chain.spectral_for``，精简缓存），之后任意目标温度/发射率
    只重算 Planck 与 t_app——与 ``chain.evaluate`` 的共公式严格一致。
    """

    def __init__(self, scn: chain.Scenario, r_ground_km: float):
        self.scn = scn
        self.st = chain.spectral_for(scn, r_ground_km)
        self.lam = np.asarray(self.st["lam_um"], dtype=float)
        self.tau = np.asarray(self.st["tau_lam"], dtype=float)
        self.lp_lam = np.asarray(self.st["l_path_lam"], dtype=float)
        t_b = float(scn.bg_temp_c) + 273.15
        self.ctx = radiometry.get_band_context(scn.band, self.lam, t_b)
        self.wtau = self.ctx.w * self.tau              # w·τ
        self.b_bg = radiometry.planck(self.lam, t_b)   # B(λ,T_bg)
        self.s_b = float(self.wtau @ self.b_bg)        # Σ w·B(T_b)·τ
        self.l_path = float(np.sum(self.ctx.w * self.lp_lam))
        self.l_b = self.s_b + self.l_path
        self.t_app_b = float(self.ctx.t_app(self.l_b))
        self.lam_eff = float(self.st["lam_eff"])
        self.tau_band = float(self.st["tau_band"])
        self.r_slant_km = float(self.st["r_slant_km"])
        self.r_ground_km = float(self.st["r_ground_km"])

    # -- 视在温差 ----------------------------------------------------------
    def dT_app(self, target_temp_c: Optional[float] = None,
               eps_t: Optional[float] = None) -> float:
        scn = self.scn
        t_t = (float(scn.target_temp_c) if target_temp_c is None
               else float(target_temp_c)) + 273.15
        e = (scn.target.eps if scn.eps_t is None else float(scn.eps_t)) \
            if eps_t is None else float(eps_t)
        b_t = radiometry.planck(self.lam, t_t)
        l_t = e * float(self.wtau @ b_t) + (1.0 - e) * self.s_b + self.l_path
        return float(self.ctx.t_app(l_t)) - self.t_app_b

    def dT_app_many(self, target_temp_c, eps_t: Optional[float] = None,
                    chunk: int = 64) -> np.ndarray:
        """一组目标温度（℃）下的视在温差数组（分块向量化 Planck）。"""
        scn = self.scn
        temps = np.atleast_1d(np.asarray(target_temp_c, dtype=float))
        e = (scn.target.eps if scn.eps_t is None else float(scn.eps_t)) \
            if eps_t is None else float(eps_t)
        out = np.empty(temps.shape, dtype=float)
        for i in range(0, temps.size, chunk):
            t_k = temps[i:i + chunk, None] + 273.15
            b_t = radiometry.planck(self.lam[None, :], t_k)      # (chunk, Nλ)
            l_t = e * (b_t @ self.wtau) + (1.0 - e) * self.s_b + self.l_path
            out[i:i + chunk] = np.array([self.ctx.t_app(v) for v in l_t]) - self.t_app_b
        return out

    # -- 任务概率 ----------------------------------------------------------
    def probabilities(self, target_temp_c: Optional[float] = None,
                      eps_t: Optional[float] = None,
                      cn2: Optional[float] = None,
                      n50_set: Optional[str] = None) -> Dict[str, np.ndarray]:
        """由本状态直接给出三任务概率（不重算大气）。"""
        scn = self.scn
        d = self.dT_app(target_temp_c, eps_t)
        return probabilities(np.array([d]), scn.sensor, self.lam_eff, self.r_slant_km,
                             scn.target.d_eff_m,
                             scn.cn2 if cn2 is None else cn2,
                             scn.n50_set if n50_set is None else n50_set)


def probabilities(d_t_app, sensor, lam_eff: float, r_slant_km: float, d_eff_m: float,
                  cn2: float, n50_set: str = "NVESD") -> Dict[str, np.ndarray]:
    """向量化正向概率：给定视在温差（可数组）→ 三任务概率数组。

    与 ``chain.evaluate`` 完全同式：r0=(0.423k²Cn²L)^(-3/5)；f_max 受 Nyquist/
    衍射/MRTD 三重限制；θ=D_eff/R_slant；N=f_max·θ；P=(N/N50)^E/(1+(N/N50)^E)。
    """
    d = np.atleast_1d(np.asarray(d_t_app, dtype=float))
    r_slant = max(float(r_slant_km), 1e-9)
    r0 = sensor_mod.fried_r0(lam_eff, cn2, r_slant * 1000.0)
    fmax = _fmax_vec(d, sensor, lam_eff, r0)
    theta = float(d_eff_m) / r_slant
    n_cyc = fmax * theta
    n50 = probability.n50_set(n50_set)
    return {task: np.asarray(probability.p_task(n_cyc, n50[task]), dtype=float)
            for task in TASKS}


def validate_fast_path(n_checks: int = 6, seed: int = 20261116,
                       verbose: bool = False) -> Dict[str, float]:
    """校核向量化快速通道（BandState/_fmax_vec）与 ``chain.evaluate`` 的一致性。"""
    rng = np.random.default_rng(seed)
    max_dp = 0.0
    max_ddt = 0.0
    for _ in range(int(n_checks)):
        band = "MWIR" if rng.random() < 0.7 else "LWIR"
        scn = chain.baseline_scenario(band=band).with_(
            aod550=float(10 ** rng.uniform(-1.5, 0.7)),
            cn2=float(10 ** rng.uniform(-17.0, -12.0)),
            pwv_cm=float(10 ** rng.uniform(-0.5, 0.9)),
            target_temp_c=float(rng.uniform(12.0, 60.0)),
        ).with_(target_key=["F16", "NIMITZ", "ALBK", "HM"][int(rng.integers(0, 4))])
        r = float(10 ** rng.uniform(-0.5, 2.4))
        ref = chain.evaluate(scn, r)
        bs = BandState(scn, r)
        d = bs.dT_app()
        pv = probabilities(np.array([d]), scn.sensor, bs.lam_eff, bs.r_slant_km,
                           scn.target.d_eff_m, scn.cn2, scn.n50_set)
        for task in TASKS:
            max_dp = max(max_dp, abs(float(pv[task][0]) - float(ref[TASK_TO_KEY[task]])))
        max_ddt = max(max_ddt, abs(d - float(ref["dT_app_K"])))
    if verbose:
        print(f"  [fast-path] max|ΔP|={max_dp:.3e}, max|Δ(ΔT_app)|={max_ddt:.3e} K", flush=True)
    return dict(max_dP=float(max_dp), max_ddT_app=float(max_ddt))


# --------------------------------------------------------------------------- #
# 热交叉盲区（规范 F12）
# --------------------------------------------------------------------------- #
def dt_curve(scn: chain.Scenario, r_km: float, task: str = "recognize",
             dT_values: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """固定距离处 P 随目标-背景固有温差 ΔT 的变化（图09 展示热交叉竖断用）。

    返回 (dT_K, P)。默认在 [−20, 20] K 内加密采样，足以看清 P→0 的窄谷。
    """
    if dT_values is None:
        dT_values = np.concatenate([
            np.linspace(-20.0, -2.0, 91), np.linspace(-2.0, 2.0, 401),
            np.linspace(2.0, 20.0, 91)])
    dts = np.asarray(dT_values, dtype=float)
    bs = BandState(scn, r_km)
    d_app = bs.dT_app_many(float(scn.bg_temp_c) + dts)
    pv = probabilities(d_app, scn.sensor, bs.lam_eff, bs.r_slant_km,
                       scn.target.d_eff_m, scn.cn2, scn.n50_set)
    return dts, np.asarray(pv[task], dtype=float)


def delta_t_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
                  p_target: float = 0.5,
                  dT_lo: float = -60.0, dT_hi: float = 80.0,
                  fine_lo: float = -10.0, fine_hi: float = 10.0,
                  fine_step: float = 0.02,
                  coarse_step: float = 0.5) -> Dict[str, object]:
    """热交叉盲区：在 r_km 处使 P<p_target 的连续 ΔT 区间 [dT_low, dT_high]。

    步骤（规范 F12）：
    1) 在 [dT_lo, dT_hi] 上粗扫（步长 0.5 K）判断盲区是否存在并定位大致范围；
    2) 在 [fine_lo, fine_hi] 上以 0.02 K 细扫（区间可扩展到粗扫边界附近）找
       P<p_target 的连续区间；
    3) 对区间两侧 P=p_target 的根在 ΔT 线性域二分至 1e-4 K。
    返回 dT_low/dT_high/blind_width_K/dT_cross_K(盲区中心)/p_min/dT_at_pmin/censored。
    """
    bs = BandState(scn, r_km)
    t_bg = float(scn.bg_temp_c)

    def _p_many(dts: np.ndarray) -> np.ndarray:
        dts = np.atleast_1d(np.asarray(dts, dtype=float))
        d_app = bs.dT_app_many(t_bg + dts)
        pv = probabilities(d_app, scn.sensor, bs.lam_eff, bs.r_slant_km,
                           scn.target.d_eff_m, scn.cn2, scn.n50_set)
        return np.asarray(pv[task], dtype=float)

    def _p_one(dt: float) -> float:
        return float(_p_many(np.array([dt]))[0])

    # ---- 1) 粗扫 ----
    coarse = np.arange(dT_lo, dT_hi + 0.5 * coarse_step, coarse_step)
    p_coarse = _p_many(coarse)
    below_c = p_coarse < p_target
    if not below_c.any():
        return dict(dT_low=float("nan"), dT_high=float("nan"), blind_width_K=0.0,
                    dT_cross_K=float("nan"), censored="全温差区间均可识别",
                    p_min=float(p_coarse.min()),
                    dT_at_pmin=float(coarse[int(np.argmin(p_coarse))]))
    if below_c.all():
        return dict(dT_low=float(dT_lo), dT_high=float(dT_hi),
                    blind_width_K=float(dT_hi - dT_lo), dT_cross_K=float(0.5 * (dT_lo + dT_hi)),
                    censored="全温差区间均不可识别（对比度不足）",
                    p_min=float(p_coarse.min()),
                    dT_at_pmin=float(coarse[int(np.argmin(p_coarse))]))
    i_min = int(np.argmin(p_coarse))
    i0 = i_min
    while i0 > 0 and below_c[i0 - 1]:
        i0 -= 1
    i1 = i_min
    while i1 < coarse.size - 1 and below_c[i1 + 1]:
        i1 += 1
    c_lo, c_hi = float(coarse[i0]), float(coarse[i1])

    # ---- 2) 细扫：[-10,10] 步长 0.02 K；必要时向粗扫边界附近扩展 ----
    parts = []
    if c_lo < fine_lo:
        parts.append(np.arange(c_lo - 0.5, fine_lo, 0.5))
    parts.append(np.arange(fine_lo, fine_hi + 1e-9, fine_step))
    if c_hi > fine_hi:
        parts.append(np.arange(fine_hi + 0.5, c_hi + 0.5, 0.5))
    fine = np.unique(np.round(np.concatenate(parts), 6))
    fine = fine[(fine >= max(dT_lo, c_lo - 1.0)) & (fine <= min(dT_hi, c_hi + 1.0))]
    p_fine = _p_many(fine)
    below_f = p_fine < p_target
    if not below_f.any():                 # 极窄盲区在 0.5 K 粗扫里被跳过时回退
        fine, p_fine, below_f = coarse, p_coarse, below_c
    i_min = int(np.argmin(p_fine))
    j0 = i_min
    while j0 > 0 and below_f[j0 - 1]:
        j0 -= 1
    j1 = i_min
    while j1 < fine.size - 1 and below_f[j1 + 1]:
        j1 += 1
    if j0 == 0 or j1 == fine.size - 1:
        lo_v, hi_v = float(fine[j0]), float(fine[j1])
        side = ("低温侧触界" if j0 == 0 else "") + ("高温侧触界" if j1 == fine.size - 1 else "")
        return dict(dT_low=lo_v, dT_high=hi_v, blind_width_K=float(hi_v - lo_v),
                    dT_cross_K=float(0.5 * (lo_v + hi_v)),
                    censored=f"盲区超出温差搜索范围（{side}）",
                    p_min=float(p_fine.min()), dT_at_pmin=float(fine[i_min]))

    # ---- 3) 两侧 P=p_target 根二分（线性域） ----
    # 低侧（负 ΔT 一侧）：ΔT 增大 → |ΔT| 减小 → P 下降，故 f=P−阈值 满足 f_lo>=0>f_hi；
    # 高侧（正 ΔT 一侧）：ΔT 增大 → |ΔT| 增大 → P 上升，f=P−阈值 为 f_lo<0<=f_hi，
    # 必须取相反符号（p_target−P）才能保证 _illinois 的 f_lo>=0>f_hi 约定。
    dt_low, _ = _illinois(lambda dt: _p_one(dt) - p_target,
                          float(fine[j0 - 1]), float(fine[j0]),
                          float(p_fine[j0 - 1] - p_target), float(p_fine[j0] - p_target),
                          coord="linear", rel_tol=DT_TOL_K)
    dt_high, _ = _illinois(lambda dt: p_target - _p_one(dt),
                           float(fine[j1]), float(fine[j1 + 1]),
                           float(p_target - p_fine[j1]), float(p_target - p_fine[j1 + 1]),
                           coord="linear", rel_tol=DT_TOL_K)
    return dict(dT_low=float(dt_low), dT_high=float(dt_high),
                blind_width_K=float(dt_high - dt_low),
                dT_cross_K=float(0.5 * (dt_low + dt_high)),
                censored="", p_min=float(p_fine.min()),
                dT_at_pmin=float(fine[i_min]))


# --------------------------------------------------------------------------- #
# 临界参数反解（单调 + 对数域二分）
# --------------------------------------------------------------------------- #
def _solve_monotone(f: Callable[[float], float], lo: float, hi: float,
                    p_target: float, increasing: bool,
                    log_domain: bool = True,
                    rel_tol: float = REL_TOL_X) -> Dict[str, object]:
    """在 [lo,hi] 上反解 f(x)=p_target（f 单调，由 increasing 指定）。

    ``log_domain=True`` 时 f 的定义域必须是正数，停止条件 |Δlnx|<=rel_tol；
    ``log_domain=False`` 时直接在 x 坐标上以绝对容差 rel_tol 停止（用于已取过
    对数的变量，如 log10 Cn²）。
    """
    f_lo, f_hi = float(f(lo)), float(f(hi))
    if increasing:
        if f_lo >= p_target:
            return dict(value=float("nan"),
                        censored=f"下限已满足（f(lo)={f_lo:.4g}≥{p_target:g}）",
                        p_at_lo=f_lo, p_at_hi=f_hi)
        if f_hi < p_target:
            return dict(value=float("nan"),
                        censored=f"上限不满足（f(hi)={f_hi:.4g}<{p_target:g}）",
                        p_at_lo=f_lo, p_at_hi=f_hi)
        g = lambda x: p_target - f(x)
        g_lo, g_hi = p_target - f_lo, p_target - f_hi
    else:
        if f_lo < p_target:
            return dict(value=float("nan"),
                        censored=f"下限已不满足（f(lo)={f_lo:.4g}<{p_target:g}）",
                        p_at_lo=f_lo, p_at_hi=f_hi)
        if f_hi >= p_target:
            return dict(value=float("nan"),
                        censored=f"上限仍满足（f(hi)={f_hi:.4g}≥{p_target:g}）",
                        p_at_lo=f_lo, p_at_hi=f_hi)
        g = lambda x: f(x) - p_target
        g_lo, g_hi = f_lo - p_target, f_hi - p_target
    x, n = _illinois(g, lo, hi, g_lo, g_hi,
                     coord="log" if log_domain else "linear", rel_tol=rel_tol)
    return dict(value=float(x), censored="", p_at_lo=f_lo, p_at_hi=f_hi, n_iter=int(n))


def aod_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
              p_target: float = 0.5, lo: float = 0.005, hi: float = 20.0) -> Dict[str, object]:
    """临界气溶胶光学厚度 AOD550（P 随 AOD 单调降）。"""
    def f(aod: float) -> float:
        return _p(scn.with_(aod550=float(aod)), r_km, task)
    return _solve_monotone(f, lo, hi, p_target, increasing=False)


def cn2_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
              p_target: float = 0.5, lo: float = 1e-18, hi: float = 1e-11) -> Dict[str, object]:
    """临界 Cn²（P 随 Cn² 单调降；在 log10 Cn² 坐标上二分）。"""
    def f(x: float) -> float:
        return _p(scn.with_(cn2=float(10.0 ** x)), r_km, task)
    res = _solve_monotone(f, math.log10(lo), math.log10(hi), p_target,
                          increasing=False, log_domain=False)
    if math.isfinite(res["value"]):
        res["value"] = float(10.0 ** res["value"])
    return res


def aperture_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
                   p_target: float = 0.5, lo: float = 0.02, hi: float = 1.0) -> Dict[str, object]:
    """临界口径 D（P 随口径单调增；达到 Nyquist 后饱和）。"""
    def f(D: float) -> float:
        return _p(scn.with_sensor(D_m=float(D)), r_km, task)
    return _solve_monotone(f, lo, hi, p_target, increasing=True)


def netd_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
               p_target: float = 0.5, lo: float = 1e-3, hi: float = 2.0) -> Dict[str, object]:
    """临界 NETD（P 随 NETD 单调降）。"""
    def f(netd: float) -> float:
        return _p(scn.with_sensor(netd_k=float(netd)), r_km, task)
    return _solve_monotone(f, lo, hi, p_target, increasing=False)


def pixel_count_for_p(scn: chain.Scenario, r_km: float, task: str = "recognize",
                      p_target: float = 0.5, npx_lo: int = 128,
                      npx_hi: int = 8192) -> Dict[str, object]:
    """临界探测器阵列规模（同 FOV 下改变 IFOV；P 随像元数单调增）。"""
    s0 = scn.sensor

    def f(npx: float) -> float:
        npx_i = int(round(float(np.clip(npx, npx_lo, npx_hi))))
        ifov = np.deg2rad(s0.fov_h_deg) / npx_i * 1e3     # mrad
        return _p(scn.with_sensor(npx_h=npx_i, ifov_mrad=ifov,
                                  f_m=s0.pitch_m / (ifov * 1e-3)), r_km, task)

    return _solve_monotone(f, float(npx_lo), float(npx_hi), p_target,
                           increasing=True, log_domain=False, rel_tol=2.0)


# --------------------------------------------------------------------------- #
# 兼容别名
# --------------------------------------------------------------------------- #
def p_curve(scn: chain.Scenario, task: str = "recognize",
            r_grid: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """任务概率随地面距离的曲线（默认 120 点对数网格）。"""
    rs = np.asarray(R_GRID if r_grid is None else r_grid, dtype=float)
    ps = np.array([_p(scn, float(r), task) for r in rs], dtype=float)
    return rs, ps


def clear_cache() -> None:
    """清空链路缓存（长跑时控制内存用）。"""
    for name in ("_band_quantities", "_spectral_cached"):
        fn = getattr(chain, name, None)
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()


if __name__ == "__main__":
    import time
    base = chain.baseline_scenario()
    t = time.time()
    print("R50(F16基线) =", r50(base), f"({time.time()-t:.2f}s)")
    t = time.time()
    print("解析天花板 =", analytic_resolution_range(base), f"({time.time()-t:.2f}s)")
    print("对比度地板 =", contrast_floor_range(base))
    print("盲区 =", delta_t_for_p(base, 10.0))
    print("快速通道一致性 =", validate_fast_path(4, verbose=True))

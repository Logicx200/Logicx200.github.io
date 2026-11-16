# -*- coding: utf-8 -*-
"""
irrecog.experiments —— 单变量（OFAT）实验矩阵、环境工况与临界状态数据产品

设计原则
--------
1. **严格单变量**：每一组实验只改变一个因子，其余全部固定为基线值（params.BASELINE）。
   长表逐行记录全部因子取值，任何一行都能独立复现。
2. **统一高精度求解器**：所有临界距离（R50/R90/R10/Rdet50/Rident50）都调用
   :mod:`irrecog.critical` 的对数域二分求解器（相对精度 1e-3），不再用粗网格插值；
   热交叉盲区与临界 AOD/Cn²/口径/NETD 同样用二分反解并带截断标记。
3. **数据产品**（与《重制实施规范》§3.3 一致）：
   - ``全工况长表/eval_long.csv.gz``：每个（工况, 目标, 距离）一行的完整链路量；
   - ``单变量对比/S00_全扫描指标汇总.csv`` 与 ``S01…S15*.csv``；
   - ``真实气候工况/环境工况_识别临界距离.csv``（8 环境 × p10/中位/p90 × 6 目标）；
   - ``临界状态/临界状态汇总.csv``（r_ref=0.9·R50 处的临界 AOD/Cn²/口径/NETD 与盲区）；
   - ``波段对比/波段对比_R50.csv``（MWIR/LWIR 双波段 R50 随 AOD/PWV 变化，供图12）；
   - ``相图/相图_AODxCn2.csv``、``相图/相图_dT_AOD.csv``（供图14/15）。

性能
----
- 长表按工况逐点评估（``chain.evaluate``），波段标量缓存使大气只算一次、多目标复用；
- 汇总/环境/临界/波段表复用长表曲线的包围信息，再对每个根做二分细化；
- 相图利用"同一 AOD 列共享大气"的物理事实：先在固定 r 网格上算一份光谱状态，
  再对 Cn² 或 ΔT 批量重算 MTF/概率（``critical.BandState``），最后做 1–2 次共享
  细化；sample 校核相对误差 < 0.5%。

运行
----
    from irrecog import experiments as E
    E.run_all("03_数据")            # 15 组 OFAT + 波段对比 + 相图（全量，数分钟）
    E.run_environments("03_数据")   # 真实气候工况矩阵
    E.run_critical_states("03_数据")# 临界状态反解
"""

import os
import time
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import chain, critical, params, probability, radiometry
from . import sensor as sensor_mod
from . import target as target_mod

ALL_TARGETS = [t["key"] for t in params.TARGETS]

#: 长表统一距离网格（地面 km，对数等距）。全量 15 组 × 6 目标 ⇒ 54 万/120 = 540 工况点
R_GRID = np.geomspace(critical.R_LO_KM, critical.R_HI_KM, 120)

#: 长表列（与 chain.evaluate 的字段保持一一对应，再加扫描标识）
LONG_SWEEP_FIELDS = ["sweep_id", "sweep_name", "sweep_value"]

#: 补充输出列（追加在汇总表末尾，不破坏原有列名）
EXTRA_FIELDS = ["lam_eff_um", "R_res_slant_km", "R_contrast_floor_km",
                "censored_R10", "censored_R90", "censored_Rdet50", "censored_Rident50"]


# --------------------------------------------------------------------------- #
# 单变量扫描定义（与既有实验设计完全一致，S01–S15）
# --------------------------------------------------------------------------- #
def sweep_defs(base: chain.Scenario) -> List[dict]:
    return [
        dict(id="S01", name="目标类型", per_target=False,
             values=[target_mod.get_target(k).name for k in ALL_TARGETS], keys=ALL_TARGETS,
             factory=lambda k: base.with_(target_key=k),
             note="6 个软件实际模型；对比不同尺寸/类别的识别极限"),
        dict(id="S02", name="波段", per_target=True,
             values=["MWIR 3.7–4.8 μm", "LWIR 8.0–12.0 μm"], keys=["MWIR", "LWIR"],
             factory=lambda b: base.with_(sensor=replace(base.sensor, band=b)),
             note="同一光学系统换波段"),
        dict(id="S03", name="目标热状态", per_target=True,
             values=[20.0, 30.0, 40.0, 50.0, 60.0], keys=[20.0, 30.0, 40.0, 50.0, 60.0],
             factory=lambda t: base.with_(target_temp_c=t),
             note="背景固定 20 ℃；20 ℃ 为热交叉状态"),
        dict(id="S04", name="气溶胶光学厚度AOD550", per_target=True,
             values=[0.02, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0, 1.6, 2.5, 4.0],
             keys=None, factory=lambda v: base.with_(aod550=v),
             note="0.02 极清洁 / 0.6 软件默认(能见度10km) / 4.0 强沙尘"),
        dict(id="S05", name="Angstrom指数", per_target=True,
             values=[0.1, 0.3, 0.5, 0.8, 1.1, 1.3, 1.6, 1.9],
             keys=None, factory=lambda v: base.with_(alpha=v),
             note="0.1–0.5 沙尘/海盐，1.1–1.6 大陆/城市，1.9 生物质燃烧"),
        dict(id="S06", name="可降水量", per_target=True,
             values=[0.2, 0.4, 0.7, 1.0, 1.28, 1.8, 2.5, 3.5, 5.0, 7.0],
             keys=None, factory=lambda v: base.with_(pwv_cm=v),
             note="0.2 高原干季 / 1.28 软件默认 / 7.0 热带海洋"),
        dict(id="S07", name="大气湍流Cn2", per_target=True,
             values=[0.0, 1e-17, 1e-16, 3e-16, 1e-15, 3e-15, 1e-14, 3e-14, 1e-13, 1e-12],
             keys=None, factory=lambda v: base.with_(cn2=v),
             note="0=软件默认不考虑湍流"),
        dict(id="S08", name="口径", per_target=True,
             values=[0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.50, 0.70],
             keys=None, factory=lambda v: base.with_sensor(D_m=v),
             note="焦距固定 → F# 随之变化"),
        dict(id="S09", name="NETD", per_target=True,
             values=[0.005, 0.01, 0.015, 0.025, 0.04, 0.06, 0.10, 0.20],
             keys=None, factory=lambda v: base.with_sensor(netd_k=v),
             note="决定对比度地板 ΔT_app = k·NETD"),
        dict(id="S10", name="IFOV探测器采样", per_target=True,
             values=[8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 32.0, 40.0],
             keys=None,
             factory=lambda v: base.with_sensor(
                 npx_h=1024, npx_v=768,
                 fov_h_deg=float(np.rad2deg(1024 * v * 1e-6)),
                 fov_v_deg=float(np.rad2deg(768 * v * 1e-6)),
                 f_m=base.sensor.pitch_m / (v * 1e-6)),
             note="改变 IFOV（等价于换焦距/换 FOV）"),
        dict(id="S11", name="平台高度", per_target=True,
             values=[100.0, 300.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 12000.0],
             keys=None, factory=lambda v: base.with_sensor(platform_h_m=v),
             note="高空下视路径短、低空水平路径长"),
        dict(id="S12", name="判据口径", per_target=True,
             values=["NVESD (4/16.5/26.6)", "经典 Johnson (2/8/16)"],
             keys=["NVESD", "JOHNSON"], factory=lambda v: base.with_(n50_set=v),
             note="两套 N50 口径相差约 2 倍"),
        dict(id="S13", name="目标尺寸口径", per_target=True,
             values=["等效方目标 sqrt(W*H)", "最大边 max(W,L,H)"],
             keys=["sqrt_area", "max_dim"], factory=lambda v: base.with_(size_rule=v),
             note="包围盒未几何标定"),
        dict(id="S14", name="目标发射率", per_target=True,
             values=[0.85, 0.88, 0.90, 0.92, 0.95, 0.97],
             keys=None, factory=lambda v: base.with_(eps_t=v),
             note="热交叉状态下发射率差是主要对比度来源"),
        dict(id="S15", name="工作模式", per_target=True,
             values=["识别通道 RECOG", "搜索通道 SEARCH"], keys=["RECOG", "SEARCH"],
             factory=lambda v: base.with_(sensor=sensor_mod.make_sensor(
                 base.band, preset=v, platform_h_m=base.sensor.platform_h_m)),
             note="软件实测搜索视场 vs 参考识别通道"),
    ]


# --------------------------------------------------------------------------- #
# 曲线与单工况汇总
# --------------------------------------------------------------------------- #
def _curve_points(scn: chain.Scenario, rows: Optional[Iterable[dict]] = None,
                  extra: Sequence[float] = (5.0, 20.0, 50.0),
                  n_scan: int = critical.N_SCAN) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """取得工况的 P(r) 曲线：优先复用长表行，否则粗扫描；再补充辅助插值点。"""
    if rows is not None:
        rows = list(rows)
        rs = np.array([float(r["r_ground_km"]) for r in rows], dtype=float)
        ps = {task: np.array([float(r[critical.TASK_TO_KEY[task]]) for r in rows], dtype=float)
              for task in critical.TASKS}
    else:
        rs, ps = critical.scan_curve(scn, n_scan)
    if extra:
        have = set(np.round(rs, 6).tolist())
        add = [float(x) for x in extra
               if round(float(x), 6) not in have and rs.min() <= float(x) <= rs.max()]
        if add:
            rows_extra = [chain.evaluate(scn, float(x)) for x in add]
            rs = np.concatenate([rs, np.array(add, dtype=float)])
            for task in critical.TASKS:
                ps[task] = np.concatenate(
                    [ps[task], np.array([float(r[critical.TASK_TO_KEY[task]]) for r in rows_extra])])
            order = np.argsort(rs)
            rs = rs[order]
            for task in critical.TASKS:
                ps[task] = ps[task][order]
    return rs, ps


def _interp_log(rs: np.ndarray, ys: np.ndarray, x: float) -> Optional[float]:
    if x < rs.min() or x > rs.max():
        return None
    return float(np.interp(math_log(x), math_log(rs), ys))


def math_log(x):
    return np.log(np.maximum(np.asarray(x, dtype=float), 1e-12))


def summarize_scn(scn: chain.Scenario, rows: Optional[Iterable[dict]] = None,
                  r_grid: Optional[np.ndarray] = None) -> Dict[str, object]:
    """单工况的临界距离汇总（高精度求解器）+ 50% 处诊断量。"""
    rs, ps = _curve_points(scn, rows, extra=() if rows is not None else (5.0, 20.0, 50.0))
    # 直接从曲线求解（rows 已给出时等价于复用曲线后再做二分细化）
    res = {name: critical.solve_from_curve(scn, task, level, rs, ps[task])
           for name, task, level in critical.LEVEL_SPECS}
    ana = critical.analytic_resolution_range(scn)
    r50 = float(res["R50_ground_km"]["r_km"])
    diag = critical.point(scn, r50) if np.isfinite(r50) else None
    eta = (r50 / ana["r_ground_km"]) if (np.isfinite(r50) and ana["r_ground_km"] > 0) else None
    p_rec = ps["recognize"]
    row = dict(
        target=scn.target_key, target_name=scn.target.name, kind=scn.target.kind,
        band=scn.band, size_rule=scn.size_rule, n50_set=scn.n50_set,
        d_eff_m=scn.target.d_eff_m, platform_h_m=scn.sensor.platform_h_m,
        target_temp_c=scn.target_temp_c, bg_temp_c=scn.bg_temp_c,
        dT_intrinsic_K=scn.dT_intrinsic_K,
        aod550=scn.aod550, alpha=scn.alpha, pwv_cm=scn.pwv_cm, cn2=scn.cn2,
        eps_t=scn.target.eps if scn.eps_t is None else scn.eps_t,
        D_m=scn.sensor.D_m, netd_k=scn.sensor.netd_k, ifov_urad=scn.sensor.ifov_urad,
        f_nyq=scn.sensor.f_nyq_cyc_mrad,
        R50_ground_km=(r50 if np.isfinite(r50) else np.nan),
        R90_ground_km=_r_or_nan(res["R90_ground_km"]["r_km"]),
        R10_ground_km=_r_or_nan(res["R10_ground_km"]["r_km"]),
        Rdet50_ground_km=_r_or_nan(res["Rdet50_ground_km"]["r_km"]),
        Rident50_ground_km=_r_or_nan(res["Rident50_ground_km"]["r_km"]),
        R_res_analytic_km=ana["r_ground_km"],
        eta=(float(eta) if eta is not None else np.nan),
        tau_at_R50=(diag["tau_band"] if diag else np.nan),
        dT_app_at_R50=(diag["dT_app_K"] if diag else np.nan),
        N_at_R50=(diag["n_cycles"] if diag else np.nan),
        fmax_at_R50=(diag["f_max"] if diag else np.nan),
        P_rec_max=float(p_rec[0]),
        P_rec_at_5km=_interp_log(rs, p_rec, 5.0),
        P_rec_at_20km=_interp_log(rs, p_rec, 20.0),
        P_rec_at_50km=_interp_log(rs, p_rec, 50.0),
        censored=res["R50_ground_km"]["censored"],
        # ---- 追加列 ----
        lam_eff_um=float(ana["lam_eff_um"]),
        R_res_slant_km=float(ana["r_slant_km"]),
        R_contrast_floor_km=np.nan,
        censored_R10=res["R10_ground_km"]["censored"],
        censored_R90=res["R90_ground_km"]["censored"],
        censored_Rdet50=res["Rdet50_ground_km"]["censored"],
        censored_Rident50=res["Rident50_ground_km"]["censored"],
    )
    return row


def _r_or_nan(v) -> float:
    v = float(v)
    return v if np.isfinite(v) else np.nan


# --------------------------------------------------------------------------- #
# 15 组 OFAT + 波段对比 + 相图（run_all.py 的 --data 只调本函数）
# --------------------------------------------------------------------------- #
def run_all(outdir: str, targets: Iterable[str] = ALL_TARGETS,
            sweep_ids: Optional[Iterable[str]] = None,
            r_grid: np.ndarray = R_GRID, verbose: bool = True,
            with_band: bool = True, with_phase: bool = True) -> Dict[str, object]:
    """运行 15 组单变量扫描，并生成长表、汇总表、波段对比与相图数据。"""
    t_start = time.time()
    base = chain.baseline_scenario()
    targets = list(targets)
    specs = sweep_defs(base)
    if sweep_ids is not None:
        keep = set(sweep_ids)
        specs = [s for s in specs if s["id"] in keep]
    long_rows: List[dict] = []
    summary_rows: List[dict] = []
    sweep_tables: Dict[str, pd.DataFrame] = {}
    errors: List[tuple] = []
    n_spec = len(specs)
    if verbose:
        print(f"  长表网格 {len(r_grid)} 点 [{r_grid[0]:.3g}, {r_grid[-1]:.3g}] km，"
              f"{n_spec} 组扫描，{len(targets)} 目标", flush=True)

    for i, spec in enumerate(specs):
        t0 = time.time()
        spec_long: List[dict] = []
        spec_tab: List[dict] = []
        keys = spec["keys"] if spec["keys"] is not None else spec["values"]
        for v, key in zip(spec["values"], keys):
            tset = [key] if not spec["per_target"] else targets
            for tk in tset:
                try:
                    scn = spec["factory"](key).with_(target_key=tk)
                    rows = chain.evaluate_many(scn, r_grid)
                    for row in rows:
                        row.update(sweep_id=spec["id"], sweep_name=spec["name"], sweep_value=v)
                    m = summarize_scn(scn, rows=rows)
                    m.update(sweep_id=spec["id"], sweep_name=spec["name"], sweep_value=v)
                except Exception as exc:  # noqa: BLE001  —— 单格失败不拖垮整轮
                    import traceback
                    traceback.print_exc()
                    errors.append((spec["id"], v, tk, str(exc)))
                    print(f"  [错误] {spec['id']} value={v} target={tk}: {exc}", flush=True)
                    continue
                spec_long.extend(rows)
                spec_tab.append(m)
        long_rows.extend(spec_long)
        summary_rows.extend(spec_tab)
        df = pd.DataFrame(spec_tab)
        sweep_tables[spec["id"]] = df
        if verbose:
            med = pd.to_numeric(df["R50_ground_km"], errors="coerce").median()
            n_cens = int(pd.to_numeric(df["R50_ground_km"], errors="coerce").isna().sum())
            print(f"  [progress {i+1}/{n_spec}] {spec['id']} {spec['name']}: "
                  f"{len(df)} 行, R50 中位={med:.4g} km, 截断 {n_cens}, "
                  f"{time.time()-t0:.1f}s", flush=True)

    os.makedirs(os.path.join(outdir, "全工况长表"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "单变量对比"), exist_ok=True)
    long_cols = list(chain.LONG_FIELDS) + LONG_SWEEP_FIELDS
    long_df = pd.DataFrame(long_rows, columns=long_cols)
    long_df.to_csv(os.path.join(outdir, "全工况长表", "eval_long.csv.gz"),
                   index=False, encoding="utf-8-sig", compression="gzip")
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(outdir, "单变量对比", "S00_全扫描指标汇总.csv"),
                   index=False, encoding="utf-8-sig")
    for sid, df in sweep_tables.items():
        name = str(df["sweep_name"].iloc[0]).replace("/", "_")
        df.to_csv(os.path.join(outdir, "单变量对比", f"{sid}_{name}.csv"),
                  index=False, encoding="utf-8-sig")
    if verbose:
        print(f"  长表 {len(long_df)} 行；汇总 {len(summary)} 行", flush=True)

    out: Dict[str, object] = dict(long=long_df, summary=summary, sweeps=sweep_tables,
                                 errors=errors)
    if errors and verbose:
        print(f"  [警告] 共 {len(errors)} 个工况点计算失败（详见上方 traceback），"
              f"长表/汇总可能缺行：{errors[:5]}", flush=True)
    if with_band:
        out["band"] = run_band_compare(outdir, targets=targets, verbose=verbose)
    if with_phase:
        out["phase"] = run_phase_maps(outdir, verbose=verbose)
    if verbose:
        print(f"  run_all 完成，总耗时 {time.time()-t_start:.1f}s", flush=True)
    return out


# --------------------------------------------------------------------------- #
# 真实气候工况矩阵
# --------------------------------------------------------------------------- #
def run_environments(outdir: str, targets: Iterable[str] = ALL_TARGETS,
                     r_grid: np.ndarray = R_GRID, verbose: bool = True) -> pd.DataFrame:
    """8 环境 × p10/中位/p90 × 6 目标的识别临界距离矩阵。"""
    targets = list(targets)
    base = chain.baseline_scenario()
    rows = []
    total = len(params.ENVIRONMENTS) * 3 * len(targets)
    k = 0
    for env in params.ENVIRONMENTS:
        for qi, qname in enumerate(("p10", "median", "p90")):
            scn0 = base.with_(aod550=env["aod"][qi], alpha=env["alpha"], pwv_cm=env["pwv"][qi])
            for tk in targets:
                k += 1
                m = summarize_scn(scn0.with_(target_key=tk))
                m.update(env_key=env["key"], env_name=env["name"], quantile=qname,
                         aod_assumed=env["aod"][qi], pwv_assumed=env["pwv"][qi],
                         alpha_assumed=env["alpha"], sites=env["sites"])
                rows.append(m)
            if verbose and (k % max(len(targets), 1) == 0):
                print(f"  [progress {k}/{total}] 环境工况 {env['key']}/{qname}", flush=True)
    df = pd.DataFrame(rows)
    os.makedirs(os.path.join(outdir, "真实气候工况"), exist_ok=True)
    df.to_csv(os.path.join(outdir, "真实气候工况", "环境工况_识别临界距离.csv"),
              index=False, encoding="utf-8-sig")
    if verbose:
        med = pd.to_numeric(df["R50_ground_km"], errors="coerce")
        print(f"  环境工况 {len(df)} 行, R50 范围 {med.min():.3g}–{med.max():.3g} km", flush=True)
    return df


# --------------------------------------------------------------------------- #
# 临界状态反解（规范 §3.3）
# --------------------------------------------------------------------------- #
def run_critical_states(outdir: str, targets: Iterable[str] = ALL_TARGETS,
                        verbose: bool = True) -> pd.DataFrame:
    """基线工况下 6 目标的临界状态表。

    参考距离按 Lead 口径取 **r_ref = 0.5·R50**（有明确裕度、P≈1，临界 AOD/Cn²/D/NETD
    才有工程解释力）；R50 截断时改用搜索边界并写 censored 说明。另附 *_at_10km
    一组附列（仅 R50>10 km 时计算），供报告用 F16@10 km 举例。
    """
    base = chain.baseline_scenario()
    rows = []
    targets = list(targets)
    for i, tk in enumerate(targets):
        t0 = time.time()
        scn = base.with_(target_key=tk)
        res = critical.range_summary(scn)
        r50 = _r_or_nan(res["R50_ground_km"]["r_km"])
        r90 = _r_or_nan(res["R90_ground_km"]["r_km"])
        ana = critical.analytic_resolution_range(scn)
        cfloor = critical.contrast_floor_range(scn)
        r50_ok = np.isfinite(r50)
        if r50_ok:
            r_ref = float(0.5 * r50)
            cens_rref = ""
        elif "近距离" in str(res["R50_ground_km"]["censored"]):
            r_ref = float(critical.R_LO_KM)
            cens_rref = "R50 近距离截断，r_ref 取搜索下限 0.2 km"
        else:
            r_ref = float(critical.R_HI_KM)
            cens_rref = "R50 超出搜索上限，r_ref 取搜索上限 400 km"
        diag = critical.point(scn, r_ref)
        dtb = critical.delta_t_for_p(scn, r_ref)
        aod = critical.aod_for_p(scn, r_ref)
        cn2 = critical.cn2_for_p(scn, r_ref)
        D = critical.aperture_for_p(scn, r_ref)
        netd = critical.netd_for_p(scn, r_ref)
        eta = (r50 / ana["r_ground_km"]) if r50_ok and ana["r_ground_km"] > 0 else np.nan
        # ---- 附列：10 km 处（仅 R50>10 km 的目标有意义）----
        if r50_ok and r50 > 10.0:
            dtb10 = critical.delta_t_for_p(scn, 10.0)
            aod10 = critical.aod_for_p(scn, 10.0)
            cn210 = critical.cn2_for_p(scn, 10.0)
            D10 = critical.aperture_for_p(scn, 10.0)
            netd10 = critical.netd_for_p(scn, 10.0)
        else:
            dtb10 = dict(dT_low=np.nan, dT_high=np.nan, blind_width_K=np.nan,
                         p_min=np.nan, dT_cross_K=np.nan, censored="R50≤10 km，不计算 10 km 附列")
            aod10 = dict(value=np.nan, censored="R50≤10 km")
            cn210 = dict(value=np.nan, censored="R50≤10 km")
            D10 = dict(value=np.nan, censored="R50≤10 km")
            netd10 = dict(value=np.nan, censored="R50≤10 km")
        rows.append(dict(
            target=tk, target_name=scn.target.name, d_eff_m=scn.target.d_eff_m,
            R50_ground_km=r50, R90_ground_km=r90,
            R_res_analytic_km=ana["r_ground_km"], eta=eta,
            r_ref_km=float(r_ref), contrast_floor_K=float(scn.sensor.delta_t_floor_k),
            AOD_crit=aod["value"], Cn2_crit=cn2["value"],
            dT_blind_low_K=dtb["dT_low"], dT_blind_high_K=dtb["dT_high"],
            dT_blind_width_K=dtb["blind_width_K"], dT_blind_pmin=dtb["p_min"],
            dT_cross_K=dtb["dT_cross_K"],
            D_crit=D["value"], NETD_crit=netd["value"],
            R_contrast_floor_km=cfloor["r_ground_km"],
            tau_at_r_ref=diag["tau_band"], dT_app_at_r_ref=diag["dT_app_K"],
            N_at_r_ref=diag["n_cycles"], fmax_at_r_ref=diag["f_max"],
            lam_eff_um=ana["lam_eff_um"], R_res_slant_km=ana["r_slant_km"],
            censored_R50=res["R50_ground_km"]["censored"],
            censored_R90=res["R90_ground_km"]["censored"],
            censored_AOD=aod["censored"], censored_Cn2=cn2["censored"],
            censored_dT=dtb["censored"], censored_D=D["censored"],
            censored_NETD=netd["censored"], censored_contrast=cfloor["censored"],
            censored_r_ref=cens_rref,
            # ---- 10 km 附列 ----
            AOD_crit_10km=aod10["value"], Cn2_crit_10km=cn210["value"],
            D_crit_10km=D10["value"], NETD_crit_10km=netd10["value"],
            dT_blind_low_10km=dtb10["dT_low"], dT_blind_high_10km=dtb10["dT_high"],
            dT_blind_width_10km=dtb10["blind_width_K"],
            dT_blind_pmin_10km=dtb10["p_min"], dT_cross_10km=dtb10["dT_cross_K"],
            censored_AOD_10km=aod10["censored"], censored_Cn2_10km=cn210["censored"],
            censored_D_10km=D10["censored"], censored_NETD_10km=netd10["censored"],
            censored_dT_10km=dtb10["censored"],
        ))
        if verbose:
            print(f"  [progress {i+1}/{len(targets)}] 临界状态 {tk}: R50={r50:.4g} km, "
                  f"r_ref(0.5R50)={r_ref:.4g} km, 盲区宽={dtb['blind_width_K']:.3g} K, "
                  f"10km 盲区宽={dtb10['blind_width_K']:.3g} K, "
                  f"AOD_crit={aod['value']:.4g}, {time.time()-t0:.1f}s", flush=True)
    df = pd.DataFrame(rows)
    os.makedirs(os.path.join(outdir, "临界状态"), exist_ok=True)
    df.to_csv(os.path.join(outdir, "临界状态", "临界状态汇总.csv"),
              index=False, encoding="utf-8-sig")
    return df


# --------------------------------------------------------------------------- #
# 波段对比（图12 专用数据）
# --------------------------------------------------------------------------- #
AOD_LEVELS = [0.02, 0.05, 0.1, 0.2, 0.35, 0.587, 1.0, 1.6, 2.5, 4.0]
PWV_LEVELS = [0.2, 0.4, 0.7, 1.0, 1.28, 1.8, 2.5, 3.5, 5.0, 7.0]
BASELINE_AOD = float(params.BASELINE["aod550"])
BASELINE_PWV = float(params.BASELINE["pwv_cm"])
BAND_COLS = ["band", "target", "aod550", "pwv_cm", "dT_intrinsic_K",
             "R50_ground_km", "R90", "R_res", "eta", "censored", "sweep_var"]


def run_band_compare(outdir: str, targets: Iterable[str] = ALL_TARGETS,
                     verbose: bool = True) -> pd.DataFrame:
    """MWIR / LWIR 双波段下 6 目标 R50 随 AOD、PWV 的变化（列见规范 §3.3）。"""
    targets = list(targets)
    base = chain.baseline_scenario()
    combos: List[Tuple[float, float, str]] = (
        [(a, BASELINE_PWV, "AOD") for a in AOD_LEVELS]
        + [(BASELINE_AOD, p, "PWV") for p in PWV_LEVELS
           if abs(p - BASELINE_PWV) > 1e-12])
    total = len(targets) * 2 * len(combos)
    rows = []
    k = 0
    for band in ("MWIR", "LWIR"):
        for tk in targets:
            for aod, pwv, var in combos:
                k += 1
                scn = base.with_(sensor=replace(base.sensor, band=band), target_key=tk,
                                 aod550=float(aod), pwv_cm=float(pwv))
                res = critical.range_summary(
                    scn, specs=(("R50", "recognize", 0.5), ("R90", "recognize", 0.9)))
                ana = critical.analytic_resolution_range(scn)
                r50 = _r_or_nan(res["R50"]["r_km"])
                r90 = _r_or_nan(res["R90"]["r_km"])
                eta = (r50 / ana["r_ground_km"]) if (np.isfinite(r50) and ana["r_ground_km"] > 0) else np.nan
                rows.append(dict(band=band, target=tk, aod550=float(aod), pwv_cm=float(pwv),
                                 dT_intrinsic_K=scn.dT_intrinsic_K,
                                 R50_ground_km=r50, R90=r90,
                                 R_res=ana["r_ground_km"], eta=eta,
                                 censored=res["R50"]["censored"], sweep_var=var))
            if verbose:
                band_df = pd.DataFrame(rows[-len(combos):])
                print(f"  [progress {k}/{total}] 波段对比 {band} {tk}: "
                      f"R50 中位={pd.to_numeric(band_df['R50_ground_km'], errors='coerce').median():.4g} km",
                      flush=True)
    df = pd.DataFrame(rows, columns=BAND_COLS)
    os.makedirs(os.path.join(outdir, "波段对比"), exist_ok=True)
    df.to_csv(os.path.join(outdir, "波段对比", "波段对比_R50.csv"),
              index=False, encoding="utf-8-sig")
    if verbose:
        print(f"  波段对比 {len(df)} 行", flush=True)
    return df


# --------------------------------------------------------------------------- #
# 相图数据（图14/15 专用；共享大气 + 一次细化）
# --------------------------------------------------------------------------- #
PHASE_TARGETS = ("F16", "NIMITZ")
PHASE_AOD = np.geomspace(0.03, 4.0, 25)          # 25 档
PHASE_CN2 = np.geomspace(1e-17, 1e-12, 21)       # 21 档
PHASE_DT = np.array([-5.0, -4.0, -3.0, -2.0, -1.0, -0.6, -0.4, -0.2, -0.1, 0.0,
                     0.1, 0.2, 0.4, 0.6, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0,
                     16.0, 20.0, 25.0, 30.0, 37.0, 45.0])   # 26 档，0 附近加密
PHASE_R_GRID = np.geomspace(critical.R_LO_KM, critical.R_HI_KM, 48)
PHASE_AOD_DT = np.geomspace(0.03, 4.0, 21)       # 相图 2 的 AOD 档（21 档）
PHASE_ROUNDS = 2                                 # 共享细化轮数（每轮 ≈ 减半括号）


def _censored_near_far(p: np.ndarray, p_target: float) -> Optional[str]:
    if p[0] < p_target:
        return "near"
    if p[-1] >= p_target:
        return "far"
    return None


def _bracket_from_ps(rs: np.ndarray, p: np.ndarray, p_target: float):
    """由 P(r) 曲线给出根的初始括号 (lo, hi, f_lo, f_hi)，f=P−p_target；无根返回 None。"""
    for j in range(1, rs.size):
        if p[j - 1] >= p_target > p[j]:
            return (float(rs[j - 1]), float(rs[j]),
                    float(p[j - 1] - p_target), float(p[j] - p_target))
    return None


def _interp_root_ln(lo: float, hi: float, f_lo: float, f_hi: float) -> float:
    """括号内 ln r 坐标上的线性内插求根（f_lo>=0>f_hi）。"""
    if f_lo == f_hi:
        return float(np.sqrt(lo * hi))
    t = f_lo / (f_lo - f_hi)                 # 0→lo 端, 1→hi 端
    t = min(max(t, 0.0), 1.0)
    return float(np.exp(np.log(lo) + t * (np.log(hi) - np.log(lo))))


def _phase_aod_cn2(outdir: str, verbose: bool) -> pd.DataFrame:
    """相图 1：AOD × Cn²；同一 (AOD, 目标) 列只算一份光谱大气。"""
    base = chain.baseline_scenario()
    rs = PHASE_R_GRID
    rows = []
    n_t = len(PHASE_TARGETS)
    n_cn = len(PHASE_CN2)
    for ti, tk in enumerate(PHASE_TARGETS):
        for ia, aod in enumerate(PHASE_AOD):
            scn = base.with_(target_key=tk, aod550=float(aod))
            # ---- 共享光谱状态：每个 r 只算一次大气 ----
            n = rs.size
            d_app = np.empty(n)
            slants = np.empty(n)
            lam_eff = None
            for k, r in enumerate(rs):
                bs = critical.BandState(scn, float(r))
                d_app[k] = bs.dT_app()
                slants[k] = bs.r_slant_km
                lam_eff = bs.lam_eff
            sens = scn.sensor
            d_eff = scn.target.d_eff_m
            n50 = scn.n50_set
            # ---- 对每个 Cn² 只重算 MTF/概率 ----
            brackets: List[Optional[tuple]] = [None] * n_cn
            for ic, cn2 in enumerate(PHASE_CN2):
                r0 = np.array([sensor_mod.fried_r0(lam_eff, float(cn2), max(s, 1e-6) * 1000.0)
                               for s in slants])
                fmax = np.array([float(sens.f_max(d_app[k], lam_eff, r0[k])) for k in range(n)])
                theta = d_eff / np.maximum(slants, 1e-9)
                n_cyc = fmax * theta
                p = np.asarray(probability.p_task(n_cyc, probability.n50_set(n50)["recognize"]),
                               dtype=float)
                brackets[ic] = _bracket_from_ps(rs, p, 0.5)
            # ---- 共享细化：每次细化所有 Cn² 的括号中点，大气按 r 只算一次 ----
            for _ in range(PHASE_ROUNDS):
                mids = [np.sqrt(b[0] * b[1]) if b is not None else None for b in brackets]
                uniq = sorted({round(m, 9) for m in mids if m is not None})
                state_at = {}
                for m in uniq:
                    state_at[m] = critical.BandState(scn, float(m))
                for ic, cn2 in enumerate(PHASE_CN2):
                    b = brackets[ic]
                    if b is None:
                        continue
                    m = round(float(mids[ic]), 9)
                    bsm = state_at[m]
                    pv = critical.probabilities(np.array([bsm.dT_app()]), sens, bsm.lam_eff,
                                                bsm.r_slant_km, d_eff, float(cn2), n50)
                    fv = float(pv["recognize"][0]) - 0.5
                    lo, hi, f_lo, f_hi = b
                    if fv >= 0.0:
                        brackets[ic] = (m, hi, fv, f_hi)
                    else:
                        brackets[ic] = (lo, m, f_lo, fv)
            for ic, cn2 in enumerate(PHASE_CN2):
                b = brackets[ic]
                r50 = _interp_root_ln(b[0], b[1], b[2], b[3]) if b is not None else np.nan
                rows.append(dict(aod550=float(aod), cn2=float(cn2), target=tk, R50=r50))
            if verbose and (ia % 5 == 0 or ia == len(PHASE_AOD) - 1):
                print(f"  [progress {ti+1}/{n_t}] 相图 AOD x Cn2 {tk}: AOD 列 {ia+1}/{len(PHASE_AOD)} "
                      f"(AOD={aod:.3g})", flush=True)
    df = pd.DataFrame(rows, columns=["aod550", "cn2", "target", "R50"])
    os.makedirs(os.path.join(outdir, "相图"), exist_ok=True)
    df.to_csv(os.path.join(outdir, "相图", "相图_AODxCn2.csv"),
              index=False, encoding="utf-8-sig")
    if verbose:
        fin = np.isfinite(df["R50"].to_numpy(dtype=float))
        print(f"  相图 AODxCn2 {len(df)} 格, 有效 {fin.sum()} 格", flush=True)
    return df


def _phase_dt_aod(outdir: str, verbose: bool) -> pd.DataFrame:
    """相图 2：ΔT × AOD（F16）；ΔT 不影响大气，同一 AOD 列只算一份光谱大气。"""
    base = chain.baseline_scenario().with_(target_key="F16")
    rs = PHASE_R_GRID
    dts = PHASE_DT
    nd = dts.size
    rows = []
    for ia, aod in enumerate(PHASE_AOD_DT):
        scn = base.with_(aod550=float(aod))
        n = rs.size
        pmat = np.empty((nd, n), dtype=float)
        # ---- 每个 r 只算一次大气，26 个 ΔT 批量重算视在温差与概率 ----
        for k, r in enumerate(rs):
            bs = critical.BandState(scn, float(r))
            d_app = bs.dT_app_many(float(scn.bg_temp_c) + dts)
            pv = critical.probabilities(d_app, scn.sensor, bs.lam_eff, bs.r_slant_km,
                                        scn.target.d_eff_m, scn.cn2, scn.n50_set)
            pmat[:, k] = pv["recognize"]
        # ---- 每个 ΔT 找根 + 共享细化（同一 r 的多个 ΔT 共用一份大气） ----
        brackets: List[Optional[tuple]] = [None] * nd
        for i in range(nd):
            brackets[i] = _bracket_from_ps(rs, pmat[i], 0.5)
        for _ in range(PHASE_ROUNDS):
            mids = [np.sqrt(b[0] * b[1]) if b is not None else None for b in brackets]
            mid_to_cells: Dict[float, List[int]] = {}
            for i, m in enumerate(mids):
                if m is not None:
                    mid_to_cells.setdefault(round(float(m), 9), []).append(i)
            for m, cells in mid_to_cells.items():
                bs = critical.BandState(scn, float(m))
                for i in cells:
                    d_app = bs.dT_app(float(scn.bg_temp_c) + float(dts[i]))
                    pv = critical.probabilities(np.array([d_app]), scn.sensor, bs.lam_eff,
                                                bs.r_slant_km, scn.target.d_eff_m,
                                                scn.cn2, scn.n50_set)
                    fv = float(pv["recognize"][0]) - 0.5
                    lo, hi, f_lo, f_hi = brackets[i]
                    if fv >= 0.0:
                        brackets[i] = (m, hi, fv, f_hi)
                    else:
                        brackets[i] = (lo, m, f_lo, fv)
        for i, dt in enumerate(dts):
            b = brackets[i]
            r50 = _interp_root_ln(b[0], b[1], b[2], b[3]) if b is not None else np.nan
            rows.append(dict(dT_K=float(dt), aod550=float(aod), target="F16", R50=r50))
        if verbose and (ia % 3 == 0 or ia == len(PHASE_AOD_DT) - 1):
            print(f"  [progress {ia+1}/{len(PHASE_AOD_DT)}] 相图 ΔT×AOD: AOD={aod:.3g}",
                  flush=True)
    df = pd.DataFrame(rows, columns=["dT_K", "aod550", "target", "R50"])
    os.makedirs(os.path.join(outdir, "相图"), exist_ok=True)
    df.to_csv(os.path.join(outdir, "相图", "相图_dT_AOD.csv"),
              index=False, encoding="utf-8-sig")
    if verbose:
        fin = np.isfinite(df["R50"].to_numpy(dtype=float))
        print(f"  相图 ΔT×AOD {len(df)} 格, 有效 {fin.sum()} 格", flush=True)
    return df


def run_phase_maps(outdir: str, verbose: bool = True) -> Dict[str, pd.DataFrame]:
    """生成 相图_AODxCn2.csv 与 相图_dT_AOD.csv（图14/15 数据源）。"""
    t0 = time.time()
    if verbose:
        print("  生成相图数据（共享大气加速）...", flush=True)
    d1 = _phase_aod_cn2(outdir, verbose)
    d2 = _phase_dt_aod(outdir, verbose)
    if verbose:
        print(f"  相图数据完成，耗时 {time.time()-t0:.1f}s", flush=True)
    return dict(aod_cn2=d1, dt_aod=d2)


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data = os.path.join(root, "03_数据")
    print("运行单变量扫描 + 波段对比 + 相图 ...", flush=True)
    run_all(data)
    print("运行真实气候工况 ...", flush=True)
    run_environments(data)
    print("运行临界状态反解 ...", flush=True)
    run_critical_states(data)
    print("完成", flush=True)

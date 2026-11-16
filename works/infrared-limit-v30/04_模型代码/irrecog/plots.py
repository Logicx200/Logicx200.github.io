# -*- coding: utf-8 -*-
"""
irrecog.plots —— 全部数据图件（正式报告版式）

图件清单（与《重制实施规范》§4 最终编号一一对应）
-------------------------------------------------
图01 模型链路与三类识别极限（分辨率天花板 / 对比度地板 / 湍流边界）
图02 工况空间：真实气候（AOD550–PWV）与软件默认工况定位
图03 斜程大气光谱透过率（由 ``plots_atmo.fig03`` 生成，本模块只负责调用）
图04 系统 MTF 链与 MRTD、f_max 判定
图05 基线任务概率曲线（6 目标，识别/探测）
图06 三任务临界距离对比（探测/识别/辨认）
图07 单变量：气溶胶 AOD550
图08 单变量：大气湍流 Cn²
图09 单变量：目标热状态与发射率（含热交叉竖断）
图10 单变量：传感器参数（口径 / NETD / IFOV）
图11 单变量：平台高度
图12 波段对比 MWIR vs LWIR（6 目标对比 + R50 随 AOD/PWV）
图13 识别极限包络：解析天花板 vs 实际 R50
图14 临界状态相图：AOD × Cn²（F16 / 尼米兹）
图15 临界状态相图：固有温差 × AOD（F16）
图16 真实气候工况热力图（8 环境 × 6 目标，p10/中位/p90）
图17 敏感性弹性排序

约定
----
- 图内不出现任何版本字样；中文使用 Microsoft YaHei；
- 全部图件 ``dpi=300, bbox_inches="tight"``，无水印；
- ``make_all(data_dir, fig_dir)`` 为总入口（保持 run_all.py 的调用方式）。
"""

import os
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
from matplotlib.lines import Line2D

from . import chain, critical, params, radiometry

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "mathtext.fontset": "dejavusans",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 110,
})

DPI = 300
TCOLOR = {"F16": "#1f77b4", "F22": "#ff7f0e", "NIMITZ": "#2ca02c",
          "ALBK": "#d62728", "HM": "#9467bd", "AGZFSC": "#8c564b"}
TNAME = {t["key"]: t["name"] for t in params.TARGETS}
TSHORT = {"F16": "F16", "F22": "F22", "NIMITZ": "尼米兹", "ALBK": "阿利伯克",
          "HM": "悍马", "AGZFSC": "爱国者"}
TORDER = ["HM", "F16", "F22", "AGZFSC", "ALBK", "NIMITZ"]
BANDCOLOR = {"MWIR": "#c0392b", "LWIR": "#2c7fb8"}
BANDLABEL = {"MWIR": "中波 MWIR 3.7–4.8 μm", "LWIR": "长波 LWIR 8.0–12.0 μm"}

#: 期望的最终图件文件名（用于清理旧编号文件；图00/图03 由他人负责，不在此列）
DESIRED_FIGS = {
    "图01_模型链路与三类极限.png",
    "图02_工况空间与默认工况定位.png",
    "图04_MTF链与MRTD.png",
    "图05_基线任务概率曲线.png",
    "图06_三任务临界距离对比.png",
    "图07_单变量_气溶胶AOD.png",
    "图08_单变量_湍流Cn2.png",
    "图09_单变量_目标热状态与发射率.png",
    "图10_单变量_传感器参数.png",
    "图11_单变量_平台高度.png",
    "图12_波段对比.png",
    "图13_识别极限包络.png",
    "图14_相图_AODxCn2.png",
    "图15_相图_温差xAOD.png",
    "图16_真实气候工况热力图.png",
    "图17_敏感性弹性排序.png",
}


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def _save(fig, outdir: str, name: str) -> str:
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {name}", flush=True)
    return path


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _read_csv(path: str, **kw) -> Optional[pd.DataFrame]:
    if not os.path.exists(path):
        print(f"  [警告] 缺少数据文件 {path}", flush=True)
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"  [警告] 读取 {path} 失败: {exc}", flush=True)
        return None


def _clean_sweeps(data_dir: str) -> Dict[str, pd.DataFrame]:
    sweeps: Dict[str, pd.DataFrame] = {}
    sdir = os.path.join(data_dir, "单变量对比")
    if not os.path.isdir(sdir):
        return sweeps
    for fn in sorted(os.listdir(sdir)):
        if fn.endswith(".csv") and fn[:3] in {f"S{i:02d}" for i in range(1, 16)}:
            sid = fn[:3]
            try:
                sweeps[sid] = pd.read_csv(os.path.join(sdir, fn), encoding="utf-8-sig")
            except Exception:  # noqa: BLE001
                continue
    return sweeps


def _censored_min_y(ylim) -> float:
    return float(ylim[0]) * 1.12 if ylim[0] > 0 else float(ylim[0]) + 1.0


def _mark_censored(ax, xs, y, color, ylim, label: Optional[str] = None):
    """在坐标轴下缘画"截断/不可识别"标记（▽）。"""
    if len(xs) == 0:
        return
    ax.plot(list(xs), [y] * len(xs), "v", ms=6, color=color, mec="k", mew=0.4,
            label=label, clip_on=False, alpha=0.9)


def _smooth_loglog(x1d: np.ndarray, y1d: np.ndarray, z: np.ndarray,
                   nx: int = 240, ny: int = 220):
    """在 log10(x)–log10(y) 平面用线性三角插值把相图网格平滑到细网格。

    约定：``z[i, j]`` 对应 ``y1d[i]``（行）与 ``x1d[j]``（列）。返回细网格 X, Y, Z；
    原数据中 NaN 的格点邻域在细网格上仍然留白（不可识别区不被插值填平）。
    """
    from scipy.interpolate import griddata, NearestNDInterpolator
    x1d = np.asarray(x1d, float)
    y1d = np.asarray(y1d, float)
    z = np.asarray(z, float)
    if z.shape != (y1d.size, x1d.size):
        return None, None, None
    Xg, Yg = np.meshgrid(x1d, y1d)                      # 与 z 同形
    ok = np.isfinite(z) & np.isfinite(Xg) & np.isfinite(Yg) & (Xg > 0) & (Yg > 0)
    if ok.sum() < 4:
        return None, None, None
    lx, ly, lz = np.log10(Xg[ok]), np.log10(Yg[ok]), z[ok]
    gx = np.linspace(lx.min(), lx.max(), nx)
    gy = np.linspace(ly.min(), ly.max(), ny)
    GX, GY = np.meshgrid(gx, gy)
    GZ = griddata(np.column_stack([lx, ly]), lz, (GX, GY), method="linear")
    finite = np.isfinite(z).astype(float)
    nn = NearestNDInterpolator(np.column_stack([np.log10(Xg).ravel(), np.log10(Yg).ravel()]),
                               finite.ravel())
    near_finite = nn(np.column_stack([GX.ravel(), GY.ravel()])).reshape(GX.shape)
    GZ = np.where(near_finite < 0.5, np.nan, GZ)
    return 10 ** GX, 10 ** GY, GZ


def _smooth_xlog_ylinear(x1d: np.ndarray, y1d: np.ndarray, z: np.ndarray,
                         nx: int = 240, ny: int = 220):
    """x 对数、y 线性坐标下的平滑插值；``z[i, j]`` ↔ ``y1d[i]`` × ``x1d[j]``。"""
    from scipy.interpolate import griddata, NearestNDInterpolator
    x1d = np.asarray(x1d, float)
    y1d = np.asarray(y1d, float)
    z = np.asarray(z, float)
    if z.shape != (y1d.size, x1d.size):
        return None, None, None
    Xg, Yg = np.meshgrid(x1d, y1d)
    ok = np.isfinite(z) & np.isfinite(Xg) & np.isfinite(Yg) & (Xg > 0)
    if ok.sum() < 4:
        return None, None, None
    lx = np.log10(Xg[ok])
    gx = np.linspace(lx.min(), lx.max(), nx)
    gy = np.linspace(float(y1d.min()), float(y1d.max()), ny)
    GX, GY = np.meshgrid(gx, gy)
    GZ = griddata(np.column_stack([lx, Yg[ok]]), z[ok], (GX, GY), method="linear")
    finite = np.isfinite(z).astype(float)
    nn = NearestNDInterpolator(np.column_stack([np.log10(Xg).ravel(), Yg.ravel()]),
                               finite.ravel())
    near_finite = nn(np.column_stack([GX.ravel(), GY.ravel()])).reshape(GX.shape)
    GZ = np.where(near_finite < 0.5, np.nan, GZ)
    return 10 ** GX, GY, GZ


def _log_ticks(lo: float, hi: float) -> List[float]:
    """在 [lo,hi] 内挑“好看”的对数刻度（按跨度自动控制疏密）。"""
    lo = max(float(lo), 1e-9)
    hi = max(float(hi), lo * 1.001)
    span = hi / lo
    if span >= 20.0:
        bases = (1.0, 2.0, 5.0)
    elif span >= 5.0:
        bases = (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
    else:
        bases = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9,
                 2.0, 2.2, 2.5, 2.8, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5,
                 6.0, 7.0, 8.0, 9.0)
    vals = set()
    for base in bases:
        for p in range(-4, 5):
            v = base * 10.0 ** p
            if lo * 0.98 <= v <= hi * 1.02:
                vals.add(round(v, 10))
    ticks = sorted(vals)
    if len(ticks) > 9:                       # 过密时抽稀（保留首末）
        step = int(np.ceil(len(ticks) / 8.0))
        ticks = ticks[::step]
        if hi * 0.98 > ticks[-1]:
            ticks[-1] = sorted(vals)[-1]
    if len(ticks) < 3:
        ticks = sorted({round(float(v), 6) for v in np.geomspace(lo, hi, 4)})
    return ticks


def _log_formatter():
    from matplotlib.ticker import FuncFormatter
    return FuncFormatter(
        lambda v, pos: (f"{v:.0f}" if v >= 10 else (f"{v:.1f}" if v >= 1 else f"{v:g}")))


def _apply_log_ticks(ax, axis: str = "y"):
    """对数轴用简洁刻度（避免 1.2×10¹ 这类冗余标注）。"""
    from matplotlib.ticker import FixedLocator, NullLocator
    axx = ax.xaxis if axis == "x" else ax.yaxis
    lo, hi = (ax.get_xlim() if axis == "x" else ax.get_ylim())
    ticks = _log_ticks(min(lo, hi), max(lo, hi))
    if len(ticks) >= 2:
        axx.set_major_locator(FixedLocator(ticks))
        axx.set_major_formatter(_log_formatter())
        axx.set_minor_locator(NullLocator())


def _log_colorbar(cb, vmin: float, vmax: float):
    """对数色标：用简洁刻度代替冗长的科学计数法。"""
    ticks = _log_ticks(vmin, vmax)
    cb.set_ticks(ticks)
    cb.ax.yaxis.set_major_formatter(_log_formatter())
    cb.ax.minorticks_off()


# --------------------------------------------------------------------------- #
# 图01 模型链路与三类极限
# --------------------------------------------------------------------------- #
def fig01_chain(outdir: str):
    fig, ax = plt.subplots(figsize=(13.4, 6.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 50)
    ax.axis("off")

    boxes = [
        (2.0, 31, 16.5, 11, "软件实测输入\n6 个目标包围盒\n背景 20 ℃ / 两档传感器", "#e8f0fb"),
        (21.5, 31, 16.5, 11, "斜程大气（球面几何）\nHITRAN2020 逐线 + 气溶胶\nτ(λ)、L$_{path}$(λ)、λ$_{eff}$", "#e6f4e6"),
        (41.0, 31, 16.5, 11, "目标/背景辐亮度\n含反射项：ΔT$_{app}$=ε$_t$·ΔB·τ\n热交叉严格发生在 ΔT=0", "#fdeee0"),
        (60.5, 31, 16.5, 11, "传感器链\nMTF → MRTD\nf$_{max}$（Nyq/衍射/MRTD）", "#e8f0fb"),
        (80.0, 31, 16.5, 11, "周期数与判据\nN = f$_{max}$·θ = f$_{max}$·D$_{eff}$/R\nTTPF：P=(N/N$_{50}$)$^E$/(1+(N/N$_{50}$)$^E$)", "#e6f4e6"),
    ]
    for (x, y, w, h, txt, c) in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.45,rounding_size=1.1",
                                    fc=c, ec="#555555", lw=1.1))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=9.0)
    for x in (18.5, 38.0, 57.5, 77.0):
        ax.add_patch(FancyArrowPatch((x, 36.5), (x + 2.7, 36.5), arrowstyle="-|>",
                                     mutation_scale=13, color="#444444", lw=1.3))

    limits = [
        (2.0, 10, "① 分辨率天花板\nR$_{res}$ = f$_{upper}$(λ$_{eff}$)·D$_{eff}$/N$_{50}$\n"
                  "pure几何，忽略大气/湍流", "#2c7fb8"),
        (35.5, 10, "② 对比度地板\n|ΔT$_{app}$| ≤ k·NETD/τ$_{opt}$ 时 f$_{max}$=0\n"
                   "任何距离、任何口径都不可识别", "#c0392b"),
        (69.0, 10, "③ 大气/湍流边界\nAOD、PWV、Cn² 使 τ↓、r$_0$↓\n"
                   "MTF 与 f$_{max}$ 提前收敛", "#8e44ad"),
    ]
    for (x, y, txt, c) in limits:
        ax.add_patch(FancyBboxPatch((x, y), 29.0, 13.0, boxstyle="round,pad=0.45,rounding_size=1.2",
                                    fc="white", ec=c, lw=1.7, ls="--"))
        ax.text(x + 14.5, y + 6.5, txt, ha="center", va="center", fontsize=8.9, color=c)
    for x in (16.75, 50.0, 83.5):
        ax.add_patch(FancyArrowPatch((x, 23.3), (x, 30.2), arrowstyle="-|>",
                                     mutation_scale=12, color="#888888", lw=1.0, ls=":"))
    ax.text(50, 3.6, "实际识别临界距离 R$_{50}$ = 三类边界共同作用结果：min(分辨率天花板, 对比度地板决定的最大距离, 大气/湍流边界)",
            ha="center", fontsize=10.6, weight="bold", color="#333333")
    ax.set_title("图 1  识别概率极限的评估链路与三类边界", fontsize=13.5, weight="bold", pad=10)
    return _save(fig, outdir, "图01_模型链路与三类极限.png")


# --------------------------------------------------------------------------- #
# 图02 工况空间
# --------------------------------------------------------------------------- #
def fig02_environment_space(outdir: str):
    fig, ax = plt.subplots(figsize=(9.0, 6.2))
    cmap = plt.get_cmap("tab10")
    for i, env in enumerate(params.ENVIRONMENTS):
        aod = np.array(env["aod"], float)
        pwv = np.array(env["pwv"], float)
        c = cmap(i % 10)
        ax.plot([pwv[0], pwv[2]], [aod[0], aod[2]], "-", color=c, lw=1.2, alpha=0.5)
        ax.plot(pwv, aod, "o", color=c, ms=4.2, alpha=0.85)
        ax.plot(pwv[1], aod[1], "o", color=c, ms=9.5, mec="k", mew=0.5,
                label=f"{env['name']}（α={env['alpha']:.2f}）")
    ax.plot(params.BASELINE["pwv_cm"], params.BASELINE["aod550"], "*", ms=21,
            color="#d62728", mec="k", mew=0.7, label="软件默认工况（能见度 10 km）")
    ax.set_xlabel("可降水量 PWV (cm)")
    ax.set_ylabel("550 nm 气溶胶光学厚度 AOD$_{550}$")
    ax.set_yscale("log")
    ax.set_title("图 2  真实气候工况空间（NASA POWER / MERRA-2, 2015–2024；小点 p10–p90，大点中位）",
                 fontsize=11.5, weight="bold")
    ax.legend(fontsize=7.6, loc="upper left", framealpha=0.92, ncol=1)
    fig.tight_layout()
    return _save(fig, outdir, "图02_工况空间与默认工况定位.png")


# --------------------------------------------------------------------------- #
# 图04 MTF / MRTD
# --------------------------------------------------------------------------- #
def fig04_mtf_mrtd(outdir: str):
    scn = chain.baseline_scenario()
    s = scn.sensor
    row_ref = chain.evaluate(scn, 20.0)
    lam = float(row_ref["lam_eff"])
    r0 = float(row_ref["r0_m"]) if np.isfinite(float(row_ref["r0_m"])) else None
    f_max_axis = max(s.f_nyq_cyc_mrad * 1.05, s.f_cut_diffraction(lam) * 1.02)
    f = np.linspace(1e-3, f_max_axis, 700)

    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.0))
    ax = axes[0]
    fc = s.f_cut_diffraction(lam)
    nu = np.clip(f / fc, 0.0, 1.0)
    comp_diff = np.where(nu < 1, (2 / np.pi) * (np.arccos(nu) - nu * np.sqrt(np.maximum(1 - nu ** 2, 0))), 0.0)
    xx = f * s.ifov_mrad
    comp_det = np.where(np.abs(xx) < 1e-12, 1.0,
                        np.abs(np.sin(np.pi * xx) / np.where(xx == 0, 1.0, np.pi * xx)))
    comp_jit = np.exp(-2 * np.pi ** 2 * s.jitter_mrad ** 2 * f ** 2)
    comp_turb = np.exp(-3.44 * (lam * 1e-6 * f * 1e3 / r0) ** (5 / 3)) if r0 else np.ones_like(f)
    comp_elec = 1.0 / (1.0 + (f / s.f_elec_cyc_mrad) ** 2)
    for comp, lab, c in ((comp_diff, "衍射", "#2c7fb8"), (comp_det, "探测器 sinc", "#e67e22"),
                         (comp_jit, "视线抖动", "#27ae60"), (comp_turb, "湍流", "#8e44ad"),
                         (comp_elec, "电子学", "#7f8c8d")):
        ax.plot(f, comp, "--", lw=1.0, color=c, alpha=0.9, label=lab)
    ax.plot(f, s.mtf(f, lam, r0), "-", lw=2.2, color="k",
            label=f"系统 MTF（含湍流, Cn²={scn.cn2:.1e}）")
    ax.plot(f, s.mtf(f, lam, None), ":", lw=1.0, color="#95a5a6", label="系统 MTF（无湍流）")
    ax.axvline(s.f_nyq_cyc_mrad, color="#c0392b", ls=":", lw=1.5)
    from matplotlib.transforms import blended_transform_factory
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    ax.text(s.f_nyq_cyc_mrad * 0.985, 0.97, f"Nyquist {s.f_nyq_cyc_mrad:.1f} cyc/mrad",
            color="#c0392b", fontsize=7.6, rotation=90, va="top", ha="right", transform=tr)
    if fc < f_max_axis:
        ax.axvline(fc, color="#7f8c8d", ls="-.", lw=1.2)
        ax.text(fc * 0.985, 0.97, f"衍射截止 {fc:.1f}", color="#7f8c8d",
                fontsize=7.6, rotation=90, va="top", ha="right", transform=tr)
    ax.set_xlabel("空间频率 (cycles/mrad)")
    ax.set_ylabel("MTF")
    ax.set_ylim(0, 1.03)
    ax.set_xlim(0, f_max_axis)
    ax.set_title(f"系统 MTF 链（MWIR，λ$_{{eff}}$={lam:.2f} μm，20 km）", fontsize=10.5)
    ax.legend(fontsize=7.2, frameon=False, loc="upper right")

    ax = axes[1]
    f2 = np.linspace(0.5, s.f_nyq_cyc_mrad, 500)
    mrtd = s.mrtd(f2, lam, r0)
    ax.semilogy(f2, mrtd * 1000, "-", lw=2.2, color="k", label="MRTD(f) = k·NETD / MTF(f)")
    lvl_max = 0.0
    for dist, c in ((5.0, "#c0392b"), (20.0, "#e67e22"), (50.0, "#2c7fb8")):
        rr = chain.evaluate(scn, dist)
        d_app = abs(float(rr["dT_app_K"]))
        lvl = s.tau_opt * d_app * 1000
        lvl_max = max(lvl_max, lvl)
        fmax = s.f_max(d_app, lam, r0)
        ax.axhline(lvl, color=c, ls="--", lw=1.2, alpha=0.9,
                   label=f"{dist:.0f} km：τ$_{{opt}}$|ΔT$_{{app}}$|={lvl:.0f} mK → f$_{{max}}$={fmax:.1f}")
        ax.plot([fmax], [lvl], "o", ms=6.5, color=c, mec="k", mew=0.5, zorder=5)
    ax.axhline(s.delta_t_floor_k * s.tau_opt * 1000, color="#7f8c8d", ls=":", lw=1.5,
               label=f"对比度地板 τ$_{{opt}}$·k·NETD={s.tau_opt * s.delta_t_floor_k * 1000:.1f} mK")
    ax.set_ylim(40, lvl_max * 2.0)
    ax.set_xlabel("空间频率 (cycles/mrad)")
    ax.set_ylabel("MRTD (mK)")
    ax.set_title("MRTD 曲线与 f$_{max}$ 判定（水平虚线为不同距离的可用对比度）", fontsize=10.2)
    ax.legend(fontsize=7.2, frameon=False, loc="lower right")
    fig.suptitle("图 4  传感器 MTF 链、MRTD 与可分辨频率上限", fontsize=13, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图04_MTF链与MRTD.png")


# --------------------------------------------------------------------------- #
# 图05 基线概率曲线
# --------------------------------------------------------------------------- #
def fig05_baseline_pd(outdir: str, data_dir: str):
    lt = _read_csv(os.path.join(data_dir, "全工况长表", "eval_long.csv.gz"),
                   usecols=["sweep_id", "target", "r_ground_km", "P_rec", "P_detect"])
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.2))
    summary = _read_csv(os.path.join(data_dir, "单变量对比", "S01_目标类型.csv"))
    markers = {}
    if summary is not None:
        for _, r in summary.iterrows():
            markers[str(r["target"])] = (float(r["R50_ground_km"]), float(r["Rdet50_ground_km"]))
    if lt is not None:
        sub = lt[lt["sweep_id"] == "S01"]
        for ax, col, key, title in zip(axes, ("P_rec", "P_detect"),
                                       (0, 1), ("识别概率 P$_{rec}$", "探测概率 P$_{det}$")):
            for tk in TORDER:
                d = sub[sub["target"] == tk].sort_values("r_ground_km")
                if d.empty:
                    continue
                r = _num(d, "r_ground_km").to_numpy()
                p = _num(d, col).to_numpy()
                ax.plot(r, p, lw=1.9, color=TCOLOR[tk], label=TSHORT[tk])
                mk = markers.get(tk)
                if mk and np.isfinite(mk[key]):
                    ax.plot([mk[key]], [0.5], "o", ms=6.5, color=TCOLOR[tk],
                            mec="k", mew=0.5, zorder=5)
            ax.axhline(0.5, color="#888888", ls=":", lw=1.1)
            ax.text(0.24, 0.515, "P = 0.5", fontsize=7.5, color="#666666")
            ax.set_xscale("log")
            ax.set_xlim(0.2, 400)
            ax.set_ylim(0, 1.02)
            ax.set_xlabel("地面距离 (km)")
            ax.set_ylabel(title)
            ax.set_title(title + "（圆点为 50% 临界距离）", fontsize=10.5)
    else:
        for ax in axes:
            ax.text(0.5, 0.5, "长表数据缺失", ha="center", va="center", transform=ax.transAxes)
    axes[0].legend(fontsize=8, loc="lower left", frameon=False)
    fig.suptitle("图 5  基线工况下 6 个软件目标的任务概率曲线（MWIR，ΔT=20 K，AOD$_{550}$=0.587）",
                 fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图05_基线任务概率曲线.png")


# --------------------------------------------------------------------------- #
# 图06 三任务临界距离
# --------------------------------------------------------------------------- #
def fig06_tasks(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    df = sweeps.get("S01")
    fig, ax = plt.subplots(figsize=(10.6, 5.2))
    if df is None:
        ax.text(0.5, 0.5, "S01 数据缺失", ha="center", va="center", transform=ax.transAxes)
        return _save(fig, outdir, "图06_三任务临界距离对比.png")
    x = np.arange(len(TORDER))
    w = 0.26
    series = [("Rdet50_ground_km", "探测 50%", "#7fb3d5", "censored_Rdet50", "censored"),
              ("R50_ground_km", "识别 50%", "#2c7fb8", "censored", "censored"),
              ("Rident50_ground_km", "辨认 50%", "#154360", "censored_Rident50", "censored")]
    ymax = 1.0
    for i, (col, lab, color, cens_col, cens_fallback) in enumerate(series):
        vals = []
        for tk in TORDER:
            sub = df[df["target"] == tk]
            v = float(_num(sub, col).iloc[0]) if len(sub) else np.nan
            vals.append(v)
        plot_v = [v if np.isfinite(v) else np.nan for v in vals]
        ax.bar(x + (i - 1) * w, plot_v, w, label=lab, color=color, edgecolor="k", linewidth=0.3)
        for xi, v in zip(x + (i - 1) * w, vals):
            if np.isfinite(v):
                ymax = max(ymax, v)
                ax.text(xi, v * 1.10, f"{v:.0f}", ha="center", fontsize=7.0)
    for xi, tk in zip(x, TORDER):
        sub = df[df["target"] == tk]
        for i, (col, lab, color, cens_col, cens_fallback) in enumerate(series):
            v = float(_num(sub, col).iloc[0]) if len(sub) else np.nan
            if np.isfinite(v):
                continue
            reason = ""
            if len(sub):
                for cc in (cens_col, cens_fallback):
                    if cc in sub.columns:
                        txt = str(sub[cc].iloc[0])
                        if txt and txt.lower() != "nan":
                            reason = txt
                            break
            short = ">400 km" if ("上限" in reason or "400" in reason) else (
                "近距不可识别" if ("近距离" in reason) else "截断")
            ax.text(xi + (i - 1) * w, 0.5, short, ha="center", va="bottom",
                    fontsize=5.8, color="#c0392b", rotation=90)
    ax.set_yscale("log")
    ax.set_ylim(0.2, ymax * 2.2)
    ax.set_xticks(x)
    ax.set_xticklabels([TSHORT[t] for t in TORDER])
    ax.set_ylabel("地面临界距离 (km)")
    ax.legend(fontsize=8.2, frameon=False, loc="upper right")
    ax.set_title("图 6  三种任务难度下的临界距离（N$_{50}$：探测 4.0 / 识别 16.5 / 辨认 26.6；"
                 "不可达者标注原因）", fontsize=11.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图06_三任务临界距离对比.png")


# --------------------------------------------------------------------------- #
# 单变量族通用绘制
# --------------------------------------------------------------------------- #
def _plot_sweep(ax, df: Optional[pd.DataFrame], xcol: str, xlabel: str,
                logx: bool = False, ycol: str = "R50_ground_km",
                ylabel: str = "识别临界距离 R$_{50}$ (km)", ylim=None,
                show_legend: bool = True):
    if df is None or df.empty:
        ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
        return
    all_y = []
    for tk in TORDER:
        sub = df[df["target"] == tk]
        if sub.empty:
            continue
        x = _num(sub, xcol)
        y = _num(sub, ycol)
        ok = x.notna() & y.notna()
        if ok.any():
            all_y.append(y[ok].to_numpy(dtype=float))
            ax.plot(x[ok], y[ok], "o-", ms=4.2, lw=1.6, color=TCOLOR[tk], label=TSHORT[tk])
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if ylim is not None:
        ax.set_ylim(ylim)
    if all_y:
        lo = min(float(np.min(a)) for a in all_y)
        hi = max(float(np.max(a)) for a in all_y)
        if ylim is None and lo > 0:
            ax.set_ylim(lo * 0.55, hi * 1.9)
    if show_legend:
        ax.legend(fontsize=7.6, frameon=False)


def fig07_aod(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    df = sweeps.get("S04")
    fig, axes = plt.subplots(1, 2, figsize=(13.4, 5.2))
    _plot_sweep(axes[0], df, "aod550", "气溶胶光学厚度 AOD$_{550}$", logx=True,
                show_legend=True)
    axes[0].set_title("识别临界距离随 AOD$_{550}$ 变化", fontsize=10.5)
    if df is not None and not df.empty:
        aod = _num(df, "aod550")
        base_aod = float(params.BASELINE["aod550"])
        for tk in TORDER:
            sub = df[df["target"] == tk].sort_values("aod550")
            if sub.empty:
                continue
            x = _num(sub, "aod550")
            y = _num(sub, "R50_ground_km")
            ref = float(np.interp(base_aod, x, y)) if y.notna().any() else np.nan
            if np.isfinite(ref) and ref > 0:
                axes[1].plot(x, (y / ref - 1.0) * 100, "o-", ms=4.0, lw=1.5,
                             color=TCOLOR[tk], label=TSHORT[tk])
        axes[1].axhline(0, color="#888888", ls=":", lw=1.0)
        axes[1].set_xscale("log")
        axes[1].set_xlabel("气溶胶光学厚度 AOD$_{550}$")
        axes[1].set_ylabel("R$_{50}$ 相对基线变化 (%)")
        axes[1].set_title(f"相对 AOD$_{{550}}$={params.BASELINE['aod550']} 的变化", fontsize=10.5)
        axes[1].legend(fontsize=7.2, frameon=False)
    fig.suptitle("图 7  单变量：气溶胶光学厚度对识别临界距离的影响", fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图07_单变量_气溶胶AOD.png")


def fig08_cn2(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    df = sweeps.get("S07")
    fig, ax = plt.subplots(figsize=(9.4, 5.6))
    plot_rows = []
    if df is not None and not df.empty:
        for tk in TORDER:
            sub = df[df["target"] == tk].copy()
            if sub.empty:
                continue
            x = _num(sub, "cn2").to_numpy(dtype=float)
            y = _num(sub, "R50_ground_km").to_numpy(dtype=float)
            xp = np.where(x <= 0, 1e-18, x)
            ok = np.isfinite(y) & (y > 0)
            if ok.any():
                ax.plot(xp[ok], y[ok], "o-", ms=4.2, lw=1.6, color=TCOLOR[tk], label=TSHORT[tk])
                plot_rows.append(y[ok])
            if (~ok).any():
                ax.plot(xp[~ok], [0.2] * int((~ok).sum()), "v", ms=6, color=TCOLOR[tk],
                        mec="k", mew=0.4, clip_on=False, alpha=0.9)
        ax.set_xscale("log")
        ax.set_xlabel("Cn² (m$^{-2/3}$)，最左点 1e-18 代表“无湍流”")
        ax.set_ylabel("识别临界距离 R$_{50}$ (km)")
        if plot_rows:
            lo = min(float(np.min(a)) for a in plot_rows)
            hi = max(float(np.max(a)) for a in plot_rows)
            ax.set_ylim(lo * 0.55, hi * 1.6)
        handles, labels = ax.get_legend_handles_labels()
        handles.append(Line2D([], [], marker="v", ls="none", color="#555555", mec="k", mew=0.4))
        labels.append("▽ = 该 Cn² 下近距离即不可识别（P<0.5）")
        ax.legend(handles, labels, fontsize=7.4, frameon=False, ncol=2)
    else:
        ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("图 8  单变量：大气湍流对识别临界距离的影响（基线 Cn²=1e-15；▽ 为不可识别）",
                 fontsize=11.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图08_单变量_湍流Cn2.png")


def fig09_thermal(outdir: str, sweeps: Dict[str, pd.DataFrame], data_dir: str):
    fig, axes = plt.subplots(1, 3, figsize=(16.4, 4.9))
    df3 = sweeps.get("S03")
    ax = axes[0]
    if df3 is not None and not df3.empty:
        bg = float(params.BASELINE["bg_temp_c"])
        for tk in TORDER:
            sub = df3[df3["target"] == tk].sort_values("target_temp_c")
            if sub.empty:
                continue
            x = _num(sub, "target_temp_c") - bg
            y = _num(sub, "R50_ground_km")
            ok = y.notna() & (y > 0)
            ax.plot(x[ok], y[ok], "o-", ms=4.5, lw=1.6, color=TCOLOR[tk], label=TSHORT[tk])
            bad = x.notna() & ~ok
            for xb in x[bad]:
                ax.plot([xb], [0.32], "X", ms=9.5, color=TCOLOR[tk], mec="k", mew=0.5,
                        clip_on=False, zorder=6)
        ax.set_yscale("log")
        ax.set_xlabel("目标-背景固有温差 ΔT (K)（背景 20 ℃）")
        ax.set_ylabel("识别临界距离 R$_{50}$ (km)")
        ax.set_xlim(0, 41)
        ax.set_ylim(0.22, None)
        ax.text(0.075, 0.025, "ΔT=0（热交叉）：P<0.5，R$_{50}$ 无解", transform=ax.transAxes,
                fontsize=7.2, color="#c0392b", va="bottom", ha="left")
        ax.legend(fontsize=6.8, frameon=False, ncol=2, loc="lower right")
        ax.set_title("目标热状态 → R$_{50}$（× = 不可识别）", fontsize=10.2)
    else:
        ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("目标热状态", fontsize=10.2)

    ax = axes[1]
    _plot_sweep(ax, sweeps.get("S14"), "eps_t", "目标发射率 ε$_t$（背景 ε$_b$=0.95）",
                show_legend=False)
    ax.set_title("发射率 → R$_{50}$", fontsize=10.2)

    # (c) 固定距离处 P 随 ΔT 的竖断（由求解器现场计算，快通道）
    ax = axes[2]
    base = chain.baseline_scenario()
    try:
        r_ref_candidates = []
        crit_df = _read_csv(os.path.join(data_dir, "临界状态", "临界状态汇总.csv"))
        if crit_df is not None and "r_ref_km" in crit_df.columns:
            for tk in ("F16", "ALBK", "NIMITZ"):
                sub = crit_df[crit_df["target"] == tk]
                if len(sub):
                    v = float(_num(sub, "r_ref_km").iloc[0])
                    if np.isfinite(v) and v > 0:
                        r_ref_candidates.append((tk, v))
        if not r_ref_candidates:
            r_ref_candidates = [("F16", 0.9 * float(critical.r50(base)))]
        for tk, r_ref in r_ref_candidates:
            scn = base.with_(target_key=tk)
            dts, ps = critical.dt_curve(scn, r_ref, "recognize")
            ax.plot(dts, ps, lw=1.9, color=TCOLOR[tk],
                    label=f"{TSHORT[tk]} @ r$_{{ref}}$={r_ref:.0f} km")
        ax.axvline(0, color="#c0392b", ls="--", lw=1.0, alpha=0.8)
        ax.set_xlabel("固有温差 ΔT (K)")
        ax.set_ylabel("识别概率 P$_{rec}$")
        ax.set_ylim(0, 1.02)
        ax.legend(fontsize=7.0, frameon=False)
        ax.set_title("热交叉竖断：ΔT=0 时 P≡0", fontsize=10.2)
    except Exception as exc:  # noqa: BLE001
        ax.text(0.5, 0.5, f"计算失败：{exc}", ha="center", va="center",
                transform=ax.transAxes, fontsize=8, wrap=True)
        ax.set_title("热交叉竖断", fontsize=10.2)
    fig.suptitle("图 9  单变量：目标热状态、发射率与热交叉盲区", fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图09_单变量_目标热状态与发射率.png")


def fig10_sensor(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 4.9))
    _plot_sweep(axes[0], sweeps.get("S08"), "D_m", "口径 D (m)", logx=True, show_legend=False)
    axes[0].set_title("口径（焦距固定，F# 随之变化）", fontsize=10.2)
    _plot_sweep(axes[1], sweeps.get("S09"), "netd_k", "NETD (K)", logx=True, show_legend=False)
    axes[1].set_title("NETD（对比度地板 k·NETD）", fontsize=10.2)
    _plot_sweep(axes[2], sweeps.get("S10"), "ifov_urad", "IFOV (μrad)", show_legend=False)
    axes[2].set_title("探测器采样 IFOV", fontsize=10.2)
    axes[2].legend(fontsize=6.8, frameon=False, ncol=2, loc="upper right")
    fig.suptitle("图 10  单变量：传感器参数对识别临界距离的影响", fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图10_单变量_传感器参数.png")


def fig11_altitude(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    fig, ax = plt.subplots(figsize=(9.4, 5.4))
    _plot_sweep(ax, sweeps.get("S11"), "platform_h_m", "平台高度 (m)", logx=True)
    ax.set_title("图 11  单变量：平台高度（高→下视短路径；低→水平长路径）",
                 fontsize=11.5, weight="bold")
    ax.legend(fontsize=7.8, frameon=False, ncol=2)
    fig.tight_layout()
    return _save(fig, outdir, "图11_单变量_平台高度.png")


# --------------------------------------------------------------------------- #
# 图12 波段对比
# --------------------------------------------------------------------------- #
def fig12_band(outdir: str, data_dir: str):
    df = _read_csv(os.path.join(data_dir, "波段对比", "波段对比_R50.csv"))
    fig = plt.figure(figsize=(16.4, 5.4))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.0, 1.0])
    # ---- (a) 6 目标双波段 R50 哑铃图 ----
    ax = fig.add_subplot(gs[0, 0])
    if df is not None and not df.empty:
        sel = df[(np.isclose(_num(df, "aod550"), float(params.BASELINE["aod550"])))
                 & (np.isclose(_num(df, "pwv_cm"), float(params.BASELINE["pwv_cm"])))]
        ypos = np.arange(len(TORDER))
        vals_all = []
        for i, tk in enumerate(TORDER):
            sub = sel[sel["target"] == tk]
            if sub.empty:
                continue
            vals = {}
            for band in ("MWIR", "LWIR"):
                s2 = sub[sub["band"] == band]
                vals[band] = float(_num(s2, "R50_ground_km").iloc[0]) if len(s2) else np.nan
            w = vals["MWIR"]
            l = vals["LWIR"]
            vals_all.extend([v for v in (w, l) if np.isfinite(v)])
            if np.isfinite(w) and np.isfinite(l):
                ax.plot([w, l], [i, i], "-", color="#bbbbbb", lw=2.0, zorder=1)
            for band, v, off in (("MWIR", w, -0.17), ("LWIR", l, 0.17)):
                if np.isfinite(v):
                    ax.plot([v], [i], "o", ms=8.5, color=BANDCOLOR[band],
                            mec="k", mew=0.5, zorder=3)
            if np.isfinite(w) and np.isfinite(l) and w > 0:
                ax.text(max(w, l) * 1.10, i, f"LWIR/MWIR={l / w:.2f}", va="center",
                        fontsize=7.4, color="#333333")
            elif not np.isfinite(l):
                ax.text(max(w, 1.0) * 1.10, i, "LWIR 不可识别", va="center",
                        fontsize=7.0, color="#c0392b")
        if vals_all:
            ax.set_xlim(min(vals_all) * 0.75, max(vals_all) * 2.4)
        ax.set_yticks(ypos)
        ax.set_yticklabels([TSHORT[t] for t in TORDER])
        ax.set_xscale("log")
        _apply_log_ticks(ax, "x")
        ax.set_xlabel("识别临界距离 R$_{50}$ (km)")
        ax.invert_yaxis()
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], marker="o", linestyle="none", color=BANDCOLOR[b],
                          mec="k", mew=0.5, label=BANDLABEL[b]) for b in ("MWIR", "LWIR")]
        ax.legend(handles=handles, fontsize=7.4, frameon=False, loc="upper right")
        ax.set_title("(a) 6 目标双波段 R$_{50}$（基线工况）", fontsize=10.3)
    else:
        ax.text(0.5, 0.5, "波段对比数据缺失", ha="center", va="center", transform=ax.transAxes)

    # ---- 代表目标：R50 随 AOD / PWV ----
    reps = ["F16", "ALBK", "NIMITZ"]
    mk = {"F16": "o", "F22": "s", "NIMITZ": "^", "ALBK": "D", "HM": "v", "AGZFSC": "P"}
    for j, (var, xcol, xlabel, title) in enumerate((
            ("AOD", "aod550", "气溶胶光学厚度 AOD$_{550}$", "(b) R$_{50}$ 随 AOD$_{550}$"),
            ("PWV", "pwv_cm", "可降水量 PWV (cm)", "(c) R$_{50}$ 随 PWV"))):
        ax = fig.add_subplot(gs[0, j + 1])
        if df is not None and not df.empty:
            sub_v = df[df["sweep_var"] == var] if "sweep_var" in df.columns else df
            for tk in reps:
                for band in ("MWIR", "LWIR"):
                    s2 = sub_v[(sub_v["target"] == tk) & (sub_v["band"] == band)]
                    s2 = s2.sort_values(xcol)
                    if s2.empty:
                        continue
                    ax.plot(_num(s2, xcol), _num(s2, "R50_ground_km"),
                            marker=mk[tk], ls="-" if band == "MWIR" else "--",
                            ms=4.2, lw=1.5, color=BANDCOLOR[band], alpha=0.9)
            from matplotlib.lines import Line2D
            h1 = [Line2D([], [], linestyle="-", color=BANDCOLOR["MWIR"], label="MWIR"),
                  Line2D([], [], linestyle="--", color=BANDCOLOR["LWIR"], label="LWIR")]
            h2 = [Line2D([], [], marker=mk[t], ls="none", color="#555555", label=TSHORT[t])
                  for t in reps]
            ax.legend(handles=h1 + h2, fontsize=7.0, frameon=False, ncol=2, loc="best")
            ax.set_xscale("log")
            ax.set_yscale("log")
            _apply_log_ticks(ax, "x")
            _apply_log_ticks(ax, "y")
            ax.set_xlabel(xlabel)
            ax.set_ylabel("R$_{50}$ (km)")
            ax.set_title(title, fontsize=10.3)
        else:
            ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
    fig.suptitle("图 12  波段对比：MWIR 3.7–4.8 μm vs LWIR 8.0–12.0 μm（同一光学系统换波段）",
                 fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图12_波段对比.png")


# --------------------------------------------------------------------------- #
# 图13 识别极限包络
# --------------------------------------------------------------------------- #
def fig13_envelope(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    df = sweeps.get("S01")
    fig, ax = plt.subplots(figsize=(10.6, 5.4))
    x = np.arange(len(TORDER))
    if df is not None and not df.empty:
        r50, rres, eta = [], [], []
        for tk in TORDER:
            sub = df[df["target"] == tk]
            r50.append(float(_num(sub, "R50_ground_km").iloc[0]) if len(sub) else np.nan)
            rres.append(float(_num(sub, "R_res_analytic_km").iloc[0]) if len(sub) else np.nan)
            eta.append(float(_num(sub, "eta").iloc[0]) if len(sub) else np.nan)
        ax.bar(x - 0.2, np.nan_to_num(rres), 0.38, label="解析天花板 R$_{res}$（纯几何）",
               color="#c6d4e8", edgecolor="k", linewidth=0.3)
        ax.bar(x + 0.2, np.nan_to_num(r50), 0.38, label="实际 R$_{50}$（含大气/湍流）",
               color="#2c7fb8", edgecolor="k", linewidth=0.3)
        for i, (a, b, e) in enumerate(zip(rres, r50, eta)):
            if np.isfinite(a) and a > 0:
                ax.text(i - 0.2, a * 1.06, f"{a:.1f}", ha="center", va="bottom", fontsize=6.8)
            if np.isfinite(b):
                ax.text(i + 0.2, b * 1.06, f"{b:.1f}", ha="center", va="bottom", fontsize=6.8,
                        color="#154360")
            if np.isfinite(a) and a > 0 and np.isfinite(b):
                ax.text(i, max(a, b) * 1.42, f"η={e:.2f}", ha="center", fontsize=8.2,
                        color="#c0392b", weight="bold")
            elif np.isfinite(b) and not np.isfinite(a):
                ax.text(i - 0.2, 0.28, "地平线下\n无解析值", ha="center", fontsize=6.4,
                        color="#c0392b", rotation=90)
            elif not np.isfinite(b):
                ax.text(i + 0.2, 0.28, "不可识别", ha="center", fontsize=7.2, color="#c0392b",
                        rotation=90)
        ax.set_yscale("log")
        ax.set_ylim(0.2, max(np.nanmax(np.array(r50, float)),
                            np.nanmax(np.array(rres, float))) * 5.0)
        ax.set_xticks(x)
        ax.set_xticklabels([TSHORT[t] for t in TORDER])
        ax.set_ylabel("距离 (km)")
        ax.legend(fontsize=8.2, frameon=False, loc="upper right")
        ax.set_title("图 13  识别极限包络：分辨率天花板 vs 实际临界距离（η=R$_{50}$/R$_{res}$）",
                     fontsize=11.5, weight="bold")
    else:
        ax.text(0.5, 0.5, "S01 数据缺失", ha="center", va="center", transform=ax.transAxes)
    fig.tight_layout()
    return _save(fig, outdir, "图13_识别极限包络.png")


# --------------------------------------------------------------------------- #
# 图14 相图 AOD × Cn²
# --------------------------------------------------------------------------- #
def fig14_phase_aod_cn2(outdir: str, data_dir: str):
    df = _read_csv(os.path.join(data_dir, "相图", "相图_AODxCn2.csv"))
    fig, axes = plt.subplots(1, 2, figsize=(14.6, 5.8))
    for ax, tk in zip(axes, ("F16", "NIMITZ")):
        if df is None or df.empty:
            ax.text(0.5, 0.5, "相图数据缺失", ha="center", va="center", transform=ax.transAxes)
            continue
        sub = df[df["target"] == tk]
        if sub.empty:
            ax.text(0.5, 0.5, f"{tk} 数据缺失", ha="center", va="center", transform=ax.transAxes)
            continue
        aod = np.sort(_num(sub, "aod550").dropna().unique())
        cn2 = np.sort(_num(sub, "cn2").dropna().unique())
        piv = sub.pivot_table(index="aod550", columns="cn2", values="R50").reindex(
            index=aod, columns=cn2)
        Z = piv.values.astype(float)
        # 每个 panel 用自己的数据范围（两目标动态范围差异大，共享色标会压扁小目标 panel）
        fin = Z[np.isfinite(Z) & (Z > 0)]
        if fin.size:
            vmin = max(0.5, float(np.percentile(fin, 1)) * 0.7)
            vmax = float(np.percentile(fin, 99)) * 1.25
        else:
            vmin, vmax = 1.0, 400.0
        norm = LogNorm(vmin=vmin, vmax=vmax)
        levels = [lv for lv in (1, 2, 3, 5, 8, 12, 16, 20, 30, 50, 80, 120, 200, 300, 400)
                  if vmin <= lv <= vmax]
        if len(levels) < 3:
            levels = list(np.geomspace(vmin, vmax, 6))
        X, Y, Zf = _smooth_loglog(cn2, aod, Z)
        if X is not None:
            cf = ax.contourf(X, Y, Zf, levels=np.geomspace(vmin, vmax, 40), cmap="viridis",
                             norm=norm, extend="both", zorder=1)
        else:
            cf = ax.contourf(cn2, aod, np.ma.masked_invalid(Z),
                             levels=np.geomspace(vmin, vmax, 30), cmap="viridis", norm=norm,
                             zorder=1)
        # 等值线直接用格点原始值绘制（不做显示平滑）
        cs = ax.contour(cn2, aod, np.ma.masked_invalid(Z), levels=levels,
                        colors="white", linewidths=0.85, linestyles="--", zorder=3)
        ax.clabel(cs, fmt=lambda v: f"{v:.0f} km", fontsize=6.8, inline_spacing=2)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Cn² (m$^{-2/3}$)")
        ax.set_ylabel("气溶胶光学厚度 AOD$_{550}$")
        ax.plot([params.BASELINE["cn2"]], [params.BASELINE["aod550"]], "*", ms=15,
                color="white", mec="k", mew=0.7, zorder=6)
        # 不可识别（NaN）格：浅灰底填充，避免被误认为漏画（仅覆盖 P<0.5、R50 无解区）
        n_nan = int(np.isnan(Z).sum())
        if n_nan:
            from scipy.interpolate import griddata as _griddata
            Xn, Yn = np.meshgrid(cn2, aod)
            nan_pts = np.isnan(Z).astype(float)
            lx = np.log10(Xn).ravel()
            ly = np.log10(Yn).ravel()
            gx = np.linspace(lx.min(), lx.max(), 260)
            gy = np.linspace(ly.min(), ly.max(), 220)
            GXm, GYm = np.meshgrid(gx, gy)
            GM = _griddata(np.column_stack([lx, ly]), nan_pts.ravel(), (GXm, GYm),
                           method="linear")
            GM = np.nan_to_num(GM, nan=0.0)
            ax.contourf(10 ** GXm, 10 ** GYm, GM, levels=[0.5, 1.5],
                        colors=["#DCDCDC"], zorder=1.5)
            ax.legend(handles=[Patch(facecolor="#DCDCDC", edgecolor="#999999",
                                     label="不可识别（P<0.5，R$_{50}$ 无解）")],
                      loc="lower left", fontsize=7.2, frameon=True, framealpha=0.9)
        ax.set_title(f"{TNAME[tk]}（D$_{{eff}}$={float(chain.baseline_scenario().with_(target_key=tk).target.d_eff_m):.1f} m）",
                     fontsize=10.5)
        cb = fig.colorbar(cf, ax=ax, pad=0.015)
        _log_colorbar(cb, vmin, vmax)
        cb.set_label("R$_{50}$ (km)（对数色标）")
    fig.suptitle("图 14  临界状态相图：气溶胶 × 湍流对识别临界距离的联合作用（基线工况，"
                 "白虚线为 R$_{50}$ 等值线）", fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图14_相图_AODxCn2.png")


# --------------------------------------------------------------------------- #
# 图15 相图 ΔT × AOD
# --------------------------------------------------------------------------- #
def fig15_phase_dt_aod(outdir: str, data_dir: str):
    df = _read_csv(os.path.join(data_dir, "相图", "相图_dT_AOD.csv"))
    fig, ax = plt.subplots(figsize=(10.2, 6.0))
    if df is None or df.empty:
        ax.text(0.5, 0.5, "相图数据缺失", ha="center", va="center", transform=ax.transAxes)
        return _save(fig, outdir, "图15_相图_温差xAOD.png")
    sub = df.copy()
    sub["dT_K"] = _num(sub, "dT_K")
    sub["aod550"] = _num(sub, "aod550")
    sub["R50"] = _num(sub, "R50")
    aod = np.sort(sub["aod550"].dropna().unique())
    dts = np.sort(sub["dT_K"].dropna().unique())
    piv = sub.pivot_table(index="dT_K", columns="aod550", values="R50").reindex(
        index=dts, columns=aod)
    Z = piv.values.astype(float)
    fin = Z[np.isfinite(Z) & (Z > 0)]
    vmin = max(0.5, float(np.percentile(fin, 2)) * 0.7) if fin.size else 1.0
    vmax = float(np.percentile(fin, 98)) * 1.3 if fin.size else 100.0
    norm = LogNorm(vmin=vmin, vmax=vmax)
    # 把不可识别带（含 ΔT=0 与近零两侧，R50 无解）单独遮出：按行划分分支
    neg_rows = [i for i, dt in enumerate(dts) if dt < 0 and np.isfinite(Z[i]).any()]
    pos_rows = [i for i, dt in enumerate(dts) if dt > 0 and np.isfinite(Z[i]).any()]
    cf = None
    for rows, sign in ((neg_rows, -1), (pos_rows, 1)):
        if len(rows) < 2:
            continue
        yy = dts[rows]
        zz = Z[rows, :]
        X, Y, Zf = _smooth_xlog_ylinear(aod, yy, zz)
        if X is None:
            continue
        cf = ax.contourf(X, Y, Zf, levels=np.geomspace(vmin, vmax, 40), cmap="magma",
                         norm=norm, extend="both", zorder=1)
    if cf is None:
        cf = ax.contourf(aod, dts, np.ma.masked_invalid(Z),
                         levels=np.geomspace(vmin, vmax, 30), cmap="magma", norm=norm, zorder=1)
    # 不可识别带：ΔT 接近 0 的行（R50 无解）
    nan_rows = [float(dt) for i, dt in enumerate(dts) if not np.isfinite(Z[i]).any()]
    near_zero = [dt for dt in nan_rows if abs(dt) < 5.0]
    band_lo = min(near_zero) if near_zero else 0.0
    band_hi = max(near_zero) if near_zero else 0.0
    slack = 0.5 * (dts[1] - dts[0]) if dts.size > 1 else 0.1
    ax.axhspan(band_lo - slack, band_hi + slack, facecolor=(1, 1, 1, 0.55), hatch="///",
               edgecolor="#999999", linewidth=0.0, zorder=2)
    ax.axhline(0.0, color="#c0392b", ls="--", lw=1.4, zorder=4)
    if near_zero:
        yr = (band_hi - slack - float(dts.min())) / max(float(dts.max() - dts.min()), 1e-9)
        ax.text(0.985, min(max(yr + 0.06, 0.05), 0.92),
                f"热交叉不可识别带（ΔT≈0，P≡0；{band_lo:+.1f}…{band_hi:+.1f} K）",
                transform=ax.transAxes, fontsize=7.8, color="#c0392b",
                ha="right", va="bottom",
                bbox=dict(fc="white", alpha=0.75, ec="none", pad=2.0), zorder=5)
    # 等值线
    clevels = [lv for lv in (2, 3, 5, 8, 12, 18, 25, 40, 60) if vmin <= lv <= vmax]
    if len(clevels) >= 2:
        cs = ax.contour(aod, dts, np.ma.masked_invalid(Z), levels=clevels,
                        colors="white", linewidths=0.8, linestyles="--", zorder=3)
        ax.clabel(cs, fmt=lambda v: f"{v:.0f} km", fontsize=6.8, inline_spacing=2)
    ax.plot([params.BASELINE["aod550"]], [float(params.BASELINE["target_temp_c"] - params.BASELINE["bg_temp_c"])],
            "*", ms=16, color="white", mec="k", mew=0.7, zorder=6)
    ax.set_xscale("log")
    ax.set_xlabel("气溶胶光学厚度 AOD$_{550}$")
    ax.set_ylabel("目标-背景固有温差 ΔT (K)（背景 20 ℃）")
    ax.set_title("图 15  临界状态相图：固有温差 × AOD$_{550}$（F16，等值线为 R$_{50}$；"
                 "阴影为热交叉不可识别带）", fontsize=11.5, weight="bold")
    cb = fig.colorbar(cf, ax=ax, pad=0.015)
    _log_colorbar(cb, vmin, vmax)
    cb.set_label("R$_{50}$ (km)（对数色标）")
    fig.tight_layout()
    return _save(fig, outdir, "图15_相图_温差xAOD.png")


# --------------------------------------------------------------------------- #
# 图16 真实气候工况热力图
# --------------------------------------------------------------------------- #
def fig16_env_heatmap(outdir: str, data_dir: str):
    df = _read_csv(os.path.join(data_dir, "真实气候工况", "环境工况_识别临界距离.csv"))
    if df is None or df.empty:
        fig, ax = plt.subplots(figsize=(9.0, 5.0))
        ax.text(0.5, 0.5, "环境工况数据缺失", ha="center", va="center", transform=ax.transAxes)
        return _save(fig, outdir, "图16_真实气候工况热力图.png")
    env_order = [e["name"] for e in params.ENVIRONMENTS]
    if "env_name" in df.columns:
        env_order = [e for e in env_order if e in set(df["env_name"])] or sorted(df["env_name"].unique())
    panels = [("p10", "p10（较乐观）"), ("median", "中位"), ("p90", "p90（较不利）")]
    mats, allv = [], []
    for q, _lab in panels:
        sub = df[df["quantile"] == q]
        piv = sub.pivot_table(index="env_name", columns="target", values="R50_ground_km",
                              aggfunc="mean").reindex(index=env_order, columns=TORDER)
        mats.append(piv.values.astype(float))
        allv.append(piv.values.astype(float))
    allcat = np.concatenate([m[np.isfinite(m)] for m in allv]) if allv else np.array([])
    vmin = float(np.percentile(allcat, 3)) * 0.8 if allcat.size else 1.0
    vmax = float(np.percentile(allcat, 97)) * 1.25 if allcat.size else 100.0
    fig, axes = plt.subplots(1, 3, figsize=(18.6, 6.0), sharey=True, layout="constrained")
    last_im = None
    for ax, (q, lab), mat in zip(axes, panels, mats):
        im = ax.imshow(np.log10(np.where(np.isfinite(mat) & (mat > 0), mat, np.nan)),
                       aspect="auto", cmap="YlOrRd", vmin=np.log10(vmin), vmax=np.log10(vmax))
        last_im = im
        ax.set_xticks(range(len(TORDER)))
        ax.set_xticklabels([TSHORT[t] for t in TORDER], rotation=20)
        if ax is axes[0]:
            ax.set_yticks(range(len(env_order)))
            ax.set_yticklabels(env_order, fontsize=8.4)
        else:
            ax.tick_params(labelleft=False)
        ax.set_title(lab, fontsize=10.5)
        ax.grid(False)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat[i, j]
                if np.isfinite(v) and v > 0:
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.6,
                            color="black" if v < np.sqrt(vmin * vmax) * 2.2 else "white")
                else:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#666666")
        ax.set_xlabel("目标")
    cb = fig.colorbar(last_im, ax=axes, pad=0.01, fraction=0.025, shrink=0.95)
    cb.set_label("log$_{10}$ R$_{50}$ (km)")
    fig.suptitle("图 16  真实气候工况下的识别临界距离（8 环境 × 6 目标；左/中/右分别为 p10 / 中位 / p90 条件，"
                 "格内数值为 R$_{50}$，单位 km）", fontsize=11.8, weight="bold")
    return _save(fig, outdir, "图16_真实气候工况热力图.png")


# --------------------------------------------------------------------------- #
# 图17 敏感性弹性排序
# --------------------------------------------------------------------------- #
def fig17_sensitivity(outdir: str, sweeps: Dict[str, pd.DataFrame]):
    specs = [("S03", "目标热状态 ΔT", "target_temp_c"),
             ("S04", "气溶胶 AOD$_{550}$", "aod550"),
             ("S05", "Ångström α", "alpha"),
             ("S06", "可降水量 PWV", "pwv_cm"),
             ("S07", "湍流 Cn²", "cn2"),
             ("S08", "口径 D", "D_m"),
             ("S09", "NETD", "netd_k"),
             ("S10", "IFOV", "ifov_urad"),
             ("S11", "平台高度", "platform_h_m"),
             ("S14", "目标发射率 ε$_t$", "eps_t")]
    base = chain.baseline_scenario()
    base_r50 = {}
    for tk in TORDER:
        base_r50[tk] = float(critical.r50(base.with_(target_key=tk)))
    rows = []
    for sid, label, _xcol in specs:
        df = sweeps.get(sid)
        if df is None or df.empty:
            continue
        factors = []
        for tk in TORDER:
            sub = df[df["target"] == tk]
            vals = _num(sub, "R50_ground_km").dropna()
            vals = vals[vals > 0]
            b = base_r50.get(tk)
            if len(vals) >= 2 and b and np.isfinite(b) and b > 0:
                factors.append(float(np.max(np.abs(np.log(vals.to_numpy() / b)))))
        if factors:
            rows.append(dict(label=label, factor=float(np.exp(np.median(factors))), sid=sid))
    # 口径/工作模式类（倍率）
    cat_specs = [("S02", "MWIR→LWIR", "band", "LWIR"),
                 ("S12", "NVESD→Johnson", "n50_set", "JOHNSON"),
                 ("S13", "sqrt(WH)→max边", "size_rule", "max_dim"),
                 ("S15", "RECOG→SEARCH", "sensor_preset", None)]
    cat_rows = []
    for sid, label, col, key in cat_specs:
        df = sweeps.get(sid)
        if df is None or df.empty or col not in df.columns:
            continue
        ratios = []
        for tk in TORDER:
            sub = df[df["target"] == tk]
            if sub.empty:
                continue
            b = base_r50.get(tk)
            if key is None:
                vals = _num(sub, "R50_ground_km").dropna()
                target_vals = vals
            else:
                mask = sub[col].astype(str) == str(key)
                vals = _num(sub[mask], "R50_ground_km").dropna()
                target_vals = vals
            if len(target_vals) and b and np.isfinite(b):
                ratios.append(float(target_vals.iloc[-1] / b))
        if ratios:
            cat_rows.append(dict(label=label, ratio=float(np.median(ratios)), sid=sid))

    fig, axes = plt.subplots(1, 2, figsize=(15.4, 5.4), gridspec_kw={"width_ratios": [1.5, 1.0]})
    ax = axes[0]
    if rows:
        d = pd.DataFrame(rows).sort_values("factor")
        colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(d)))
        ax.barh(d["label"], d["factor"] - 1.0, left=1.0, color=colors,
                edgecolor="k", linewidth=0.3)
        for i, (v, sid) in enumerate(zip(d["factor"], d["sid"])):
            ax.text(v * 1.03, i, f"{v:.2f}×  [{sid}]", va="center", fontsize=8.0)
        ax.set_xscale("log")
        ax.set_xlim(0.95, float(d["factor"].max()) * 1.6)
        _apply_log_ticks(ax, "x")
        ax.set_xlabel("识别临界距离 R$_{50}$ 的最大相对变化倍率（中位，相对基线；1.0=无变化）")
        ax.set_title("(a) 连续单变量的弹性排序（越大越敏感）", fontsize=10.5)
        ax.grid(axis="x", alpha=0.25)
    else:
        ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
    ax = axes[1]
    if cat_rows:
        d2 = pd.DataFrame(cat_rows)
        y = np.arange(len(d2))
        ax.barh(y, d2["ratio"] - 1.0, left=1.0, color="#c0392b", alpha=0.85,
                edgecolor="k", linewidth=0.3)
        ax.axvline(1.0, color="#333333", ls="--", lw=1.0)
        ax.set_yticks(y)
        ax.set_yticklabels(d2["label"], fontsize=8.4)
        for i, (v, sid) in enumerate(zip(d2["ratio"], d2["sid"])):
            ax.text(v + 0.03, i, f"{v:.2f}×  [{sid}]", va="center", fontsize=8.0)
        ax.set_xlim(0.55, max(2.2, float(d2["ratio"].max()) * 1.25))
        ax.set_xlabel("R$_{50}$ 相对基线倍率（中位；1.0=与基线相同）")
        ax.set_title("(b) 口径/波段/工作模式类切换的倍率", fontsize=10.5)
    else:
        ax.text(0.5, 0.5, "数据缺失", ha="center", va="center", transform=ax.transAxes)
    fig.suptitle("图 17  敏感性排序：哪些单变量最能移动识别临界距离", fontsize=12.5, weight="bold")
    fig.tight_layout()
    return _save(fig, outdir, "图17_敏感性弹性排序.png")


# --------------------------------------------------------------------------- #
# 旧编号图件清理
# --------------------------------------------------------------------------- #
def _cleanup_old_numbering(fig_dir: str):
    """删除图01/02/04–17 中不在最终清单内的旧编号文件（图00/图03 不动）。"""
    if not os.path.isdir(fig_dir):
        return
    keep_nums = {"01", "02", "04", "05", "06", "07", "08", "09", "10", "11",
                 "12", "13", "14", "15", "16", "17"}
    removed = []
    for fn in os.listdir(fig_dir):
        if not fn.startswith("图") or not fn.endswith((".png", ".pdf")):
            continue
        num = fn[1:3]
        if num not in keep_nums:
            continue
        if num in ("03",):
            continue
        if fn in DESIRED_FIGS:
            continue
        try:
            os.remove(os.path.join(fig_dir, fn))
            removed.append(fn)
        except OSError:
            pass
    if removed:
        print("  清理旧编号图件: " + ", ".join(removed), flush=True)
    # 图03 改名后的旧文件（新文件由 plots_atmo 生成后清理旧名）
    new03 = os.path.join(fig_dir, "图03_斜程大气光谱透过率.png")
    old03 = os.path.join(fig_dir, "图03_光谱大气透过率.png")
    if os.path.exists(new03) and os.path.exists(old03):
        try:
            os.remove(old03)
            print("  清理旧图03: 图03_光谱大气透过率.png", flush=True)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# 图03（大气光谱，由 plots_atmo 负责）
# --------------------------------------------------------------------------- #
def _call_fig03(fig_dir: str):
    try:
        from . import plots_atmo
        plots_atmo.fig03(fig_dir)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [提示] 图03 暂未生成（plots_atmo 未就绪或报错：{exc}）", flush=True)
        return False


# --------------------------------------------------------------------------- #
# 总入口
# --------------------------------------------------------------------------- #
def make_all(data_dir: str, fig_dir: str, verbose: bool = True):
    """生成 图01/02/04–17 并调用 图03；返回已生成文件列表。"""
    os.makedirs(fig_dir, exist_ok=True)
    sweeps = _clean_sweeps(data_dir)
    if verbose:
        print(f"读取单变量扫描表：{sorted(sweeps.keys())}", flush=True)
    made: List[str] = []

    def run(fn, name, *args):
        try:
            made.append(fn(*args))
        except Exception as exc:  # noqa: BLE001
            import traceback
            print(f"  [错误] {name} 生成失败: {exc}", flush=True)
            traceback.print_exc()

    if verbose:
        print("[progress 1/17] 图01 链路图", flush=True)
    run(fig01_chain, "图01", fig_dir)
    if verbose:
        print("[progress 2/17] 图02 工况空间", flush=True)
    run(fig02_environment_space, "图02", fig_dir)
    _call_fig03(fig_dir)
    if verbose:
        print("[progress 4/17] 图04 MTF/MRTD", flush=True)
    run(fig04_mtf_mrtd, "图04", fig_dir)
    if verbose:
        print("[progress 5/17] 图05 基线概率曲线", flush=True)
    run(fig05_baseline_pd, "图05", fig_dir, data_dir)
    if verbose:
        print("[progress 6/17] 图06 三任务临界距离", flush=True)
    run(fig06_tasks, "图06", fig_dir, sweeps)
    if verbose:
        print("[progress 7/17] 图07 气溶胶", flush=True)
    run(fig07_aod, "图07", fig_dir, sweeps)
    if verbose:
        print("[progress 8/17] 图08 湍流", flush=True)
    run(fig08_cn2, "图08", fig_dir, sweeps)
    if verbose:
        print("[progress 9/17] 图09 热状态/发射率", flush=True)
    run(fig09_thermal, "图09", fig_dir, sweeps, data_dir)
    if verbose:
        print("[progress 10/17] 图10 传感器参数", flush=True)
    run(fig10_sensor, "图10", fig_dir, sweeps)
    if verbose:
        print("[progress 11/17] 图11 平台高度", flush=True)
    run(fig11_altitude, "图11", fig_dir, sweeps)
    if verbose:
        print("[progress 12/17] 图12 波段对比", flush=True)
    run(fig12_band, "图12", fig_dir, data_dir)
    if verbose:
        print("[progress 13/17] 图13 识别极限包络", flush=True)
    run(fig13_envelope, "图13", fig_dir, sweeps)
    if verbose:
        print("[progress 14/17] 图14 相图 AOD x Cn2", flush=True)
    run(fig14_phase_aod_cn2, "图14", fig_dir, data_dir)
    if verbose:
        print("[progress 15/17] 图15 相图 ΔT×AOD", flush=True)
    run(fig15_phase_dt_aod, "图15", fig_dir, data_dir)
    if verbose:
        print("[progress 16/17] 图16 环境热力图", flush=True)
    run(fig16_env_heatmap, "图16", fig_dir, data_dir)
    if verbose:
        print("[progress 17/17] 图17 敏感性排序", flush=True)
    run(fig17_sensitivity, "图17", fig_dir, sweeps)
    _cleanup_old_numbering(fig_dir)
    if verbose:
        print(f"图件完成：{len(made)} 张已生成", flush=True)
    return made


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    make_all(os.path.join(root, "03_数据"), os.path.join(root, "02_图表"))

# -*- coding: utf-8 -*-
"""
irsim.experiments —— 工况定义、LHS/GP 代理模型、Morris/Sobol 敏感性、
临界边界（等性能曲线）与相图网格计算。
"""

from dataclasses import replace
import numpy as np
import pandas as pd
from scipy.stats import qmc
from scipy.optimize import brentq, minimize

from . import model as m


# --------------------------------------------------------------------------- #
# 工况定义（与实验设计方案 4.3 节一致）
# --------------------------------------------------------------------------- #
BASE = dict(mor=23.0, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR")

CASES = [
    dict(id="A0",  desc="基准", mor=23.0, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    # B 单因子
    dict(id="B1",  desc="MOR=20", mor=20.0, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B2",  desc="MOR=10", mor=10.0, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B3",  desc="MOR=5",  mor=5.0,  alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B4",  desc="MOR=2",  mor=2.0,  alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B5",  desc="MOR=0.5", mor=0.5, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B6",  desc="alpha=0",   mor=23.0, alpha=0.0, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B7",  desc="alpha=0.5", mor=23.0, alpha=0.5, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B8",  desc="alpha=1.0", mor=23.0, alpha=1.0, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B9",  desc="alpha=1.6", mor=23.0, alpha=1.6, w=1.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B10", desc="w=0.5", mor=23.0, alpha=1.3, w=0.5, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B11", desc="w=3.0", mor=23.0, alpha=1.3, w=3.0, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B12", desc="w=5.0", mor=23.0, alpha=1.3, w=5.0, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="B13", desc="Cn2=1e-16", mor=23.0, alpha=1.3, w=1.5, cn2=1e-16, dT=10.0, band="LWIR"),
    dict(id="B14", desc="Cn2=1e-15", mor=23.0, alpha=1.3, w=1.5, cn2=1e-15, dT=10.0, band="LWIR"),
    dict(id="B15", desc="Cn2=1e-13", mor=23.0, alpha=1.3, w=1.5, cn2=1e-13, dT=10.0, band="LWIR"),
    dict(id="B16", desc="dT=3", mor=23.0, alpha=1.3, w=1.5, cn2=1e-14, dT=3.0, band="LWIR"),
    dict(id="B17", desc="MWIR", mor=23.0, alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, band="MWIR"),
    # C 组合/极端
    dict(id="C1", desc="浓雾+强湍流", mor=0.8, alpha=0.0, w=3.0, cn2=1e-13, dT=10.0, band="LWIR"),
    dict(id="C2", desc="城市霾+低对比", mor=3.0, alpha=1.5, w=2.0, cn2=1e-14, dT=3.0, band="LWIR"),
    dict(id="C3", desc="沙尘+MWIR", mor=4.0, alpha=0.3, w=1.0, cn2=1e-14, dT=10.0, band="MWIR"),
    dict(id="C4", desc="雨等效", mor=8.0, alpha=0.0, w=4.0, cn2=1e-14, dT=10.0, band="LWIR"),
    dict(id="C5", desc="晴空+强湍流", mor=23.0, alpha=1.3, w=1.5, cn2=1e-13, dT=10.0, band="LWIR"),
    dict(id="C6", desc="干冷/逆温", mor=5.0, alpha=1.3, w=0.5, cn2=1e-16, dT=3.0, band="LWIR"),
]


def run_cases(sensor, target, R_eval=4.0):
    rows = []
    for c in CASES:
        atmo = m.Atmo(mor=c["mor"], alpha=c["alpha"], w=c["w"], cn2=c["cn2"])
        tgt = m.Target(size=target.size, dT=c["dT"], area=target.area)
        ev = m.evaluate_at_range(atmo, c["band"], R_eval, sensor, tgt)
        r50 = m.range_for_pd(atmo, c["band"], sensor, tgt, 0.5)
        r90 = m.range_for_pd(atmo, c["band"], sensor, tgt, 0.9)
        rdet = m.range_for_pd(atmo, c["band"], sensor, tgt, 0.5,
                              n50=sensor.n50_detect, Rmax=80.0)
        rows.append(dict(
            case=c["id"], desc=c["desc"], band=c["band"],
            mor=c["mor"], alpha=c["alpha"], w=c["w"], cn2=c["cn2"], dT=c["dT"],
            tau_band=ev["tau_band"], lam_eff=ev["lam_eff"], r0=ev["r0"],
            dT_app=ev["dT_app"], fmax=ev["fmax"], n_cycles=ev["n"],
            pd_at_4km=ev["pd"], pd_detect_at_4km=ev["pd_detect"],
            R50_km=r50, R90_km=r90, Rdet_km=rdet,
        ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 参数空间与 LHS
# --------------------------------------------------------------------------- #
# 物理参数：mor, alpha, w, cn2, dT
PARAM_NAMES = ["MOR", "alpha", "w", "Cn2", "dT"]
PARAM_BOUNDS = {
    "MOR":   (0.5, 23.0, "log"),
    "alpha": (0.0, 1.6, "lin"),
    "w":     (0.5, 5.0, "lin"),
    "Cn2":   (1e-16, 1e-13, "log"),
    "dT":    (3.0, 10.0, "lin"),
}


def to_unit(values):
    """物理值 -> [0,1]^d。values: dict name->scalar or dict name->array。"""
    out = []
    for name in PARAM_NAMES:
        lo, hi, scale = PARAM_BOUNDS[name]
        v = np.asarray(values[name], dtype=float)
        if scale == "log":
            u = (np.log10(v) - np.log10(lo)) / (np.log10(hi) - np.log10(lo))
        else:
            u = (v - lo) / (hi - lo)
        out.append(u)
    return np.stack(out, axis=-1)


def from_unit(u):
    """[0,1]^d -> 物理值 dict。u: (..., d)。"""
    u = np.asarray(u, dtype=float)
    out = {}
    for i, name in enumerate(PARAM_NAMES):
        lo, hi, scale = PARAM_BOUNDS[name]
        if scale == "log":
            out[name] = 10 ** (np.log10(lo) + u[..., i] * (np.log10(hi) - np.log10(lo)))
        else:
            out[name] = lo + u[..., i] * (hi - lo)
    return out


def make_lhs(n_per_band=150, seed=2026):
    """每个波段各 n 点 LHS（5 维物理参数）。"""
    sampler = qmc.LatinHypercube(d=len(PARAM_NAMES), seed=seed)
    rows = []
    for band in ["LWIR", "MWIR"]:
        u = sampler.random(n_per_band)
        vals = from_unit(u)
        for k in range(n_per_band):
            rows.append(dict(
                band=band,
                mor=float(vals["MOR"][k]), alpha=float(vals["alpha"][k]),
                w=float(vals["w"][k]), cn2=float(vals["Cn2"][k]),
                dT=float(vals["dT"][k]),
            ))
    return pd.DataFrame(rows)


def metrics_for_sample(row, sensor, target, R_eval=4.0):
    atmo = m.Atmo(mor=row["mor"], alpha=row["alpha"], w=row["w"], cn2=row["cn2"])
    tgt = m.Target(size=target.size, dT=row["dT"], area=target.area)
    ev = m.evaluate_at_range(atmo, row["band"], R_eval, sensor, tgt)
    r50 = m.range_for_pd(atmo, row["band"], sensor, tgt, 0.5)
    rdet = m.range_for_pd(atmo, row["band"], sensor, tgt, 0.5,
                          n50=sensor.n50_detect, Rmax=80.0)
    return dict(tau_band=ev["tau_band"], dT_app=ev["dT_app"],
                fmax=ev["fmax"], n_cycles=ev["n"], pd_at_4km=ev["pd"],
                R50_km=r50, Rdet_km=rdet)


def run_lhs(sensor, target):
    df = make_lhs()
    rows = []
    for _, row in df.iterrows():
        mm = metrics_for_sample(row, sensor, target)
        rows.append({**row.to_dict(), **mm})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# GP 代理模型（RBF 核，逐维长度尺度，最大化边际似然）
# --------------------------------------------------------------------------- #
class GP:
    def __init__(self, jitter=1e-6):
        self.jitter = jitter
        self.ls = None
        self.y_mean = 0.0
        self.y_std = 1.0

    def _kernel(self, X1, X2):
        d2 = ((X1[:, None, :] - X2[None, :, :]) / self.ls) ** 2
        return np.exp(-0.5 * d2.sum(-1))

    def fit(self, X, y):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.y_mean = float(np.mean(y))
        self.y_std = float(np.std(y)) + 1e-12
        yn = (y - self.y_mean) / self.y_std
        self.ls = np.full(X.shape[1], 0.35)

        def nll(log_ls):
            self.ls = np.exp(log_ls)
            K = self._kernel(X, X) + self.jitter * np.eye(len(X))
            try:
                L = np.linalg.cholesky(K)
            except np.linalg.LinAlgError:
                return 1e10
            alpha = np.linalg.solve(L.T, np.linalg.solve(L, yn))
            return float(0.5 * yn @ alpha + np.sum(np.log(np.diag(L))) + 0.5 * len(X) * np.log(2 * np.pi))

        res = minimize(nll, np.log(self.ls), method="L-BFGS-B",
                       bounds=[(-3.0, 2.5)] * X.shape[1])
        self.ls = np.exp(res.x)
        K = self._kernel(X, X) + self.jitter * np.eye(len(X))
        L = np.linalg.cholesky(K)
        self.alpha = np.linalg.solve(L.T, np.linalg.solve(L, yn))
        self.X_train = X
        return self

    def predict(self, X):
        X = np.asarray(X, float)
        Ks = self._kernel(X, self.X_train)
        return Ks @ self.alpha * self.y_std + self.y_mean


def gp_cv_r2(X, y, folds=5, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(X))
    chunks = np.array_split(idx, folds)
    pred = np.empty_like(np.asarray(y, float))
    for ch in chunks:
        tr = np.setdiff1d(idx, ch)
        gp = GP().fit(np.asarray(X)[tr], np.asarray(y)[tr])
        pred[ch] = gp.predict(np.asarray(X)[ch])
    y = np.asarray(y, float)
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return float(1 - ss_res / ss_tot), pred


# --------------------------------------------------------------------------- #
# Morris 筛选
# --------------------------------------------------------------------------- #
def morris(func_unit, d, r=10, p=4, seed=0):
    """func_unit: 输入 [0,1]^d -> 标量；返回 mu, mu_star, sigma。"""
    rng = np.random.default_rng(seed)
    delta = p / (2.0 * (p - 1))
    EEs = np.zeros((r, d))
    for t in range(r):
        x = rng.uniform(0.0, 1.0 - delta, d)
        f0 = func_unit(x)
        order = rng.permutation(d)
        for i in order:
            step = rng.choice([-delta, delta])
            xn = x.copy()
            if xn[i] + step < 0 or xn[i] + step > 1:
                step = -step
            xn[i] += step
            f1 = func_unit(xn)
            EEs[t, i] = (f1 - f0) / step
            x, f0 = xn, f1
    return dict(mu=EEs.mean(axis=0), mu_star=np.abs(EEs).mean(axis=0),
                sigma=EEs.std(axis=0))


# --------------------------------------------------------------------------- #
# Sobol 指数（Saltelli 2010 估计，作用于代理模型）
# --------------------------------------------------------------------------- #
def sobol_indices(func_unit, d, N=1024, seed=0):
    rng = np.random.default_rng(seed)
    A = rng.random((N, d))
    B = rng.random((N, d))
    fA = np.asarray([func_unit(a) for a in A])
    fB = np.asarray([func_unit(b) for b in B])
    var = np.var(np.concatenate([fA, fB]))
    S = np.zeros(d)
    ST = np.zeros(d)
    for i in range(d):
        ABi = A.copy()
        ABi[:, i] = B[:, i]
        fABi = np.asarray([func_unit(a) for a in ABi])
        S[i] = np.mean(fB * (fABi - fA)) / var
        ST[i] = 0.5 * np.mean((fA - fABi) ** 2) / var
    return dict(S1=np.clip(S, 0, 1), ST=np.clip(ST, 0, 1))


# --------------------------------------------------------------------------- #
# 临界边界（等性能曲线）
# --------------------------------------------------------------------------- #
def _atmo_from(mor, alpha, w, cn2):
    return m.Atmo(mor=mor, alpha=alpha, w=w, cn2=cn2)


def critical_mor(alpha, R_target, band, sensor, target,
                 w=1.5, cn2=1e-14, dT=10.0, lo=0.4, hi=23.0, n50=None):
    def g(mor):
        r = m.range_for_pd(_atmo_from(mor, alpha, w, cn2), band, sensor, target,
                           0.5, n50=n50)
        if not np.isfinite(r):
            return -R_target
        return r - R_target
    if g(lo) > 0 or g(hi) < 0:
        return float("nan")
    return float(brentq(g, lo, hi, xtol=1e-3))


def critical_cn2(mor, R_target, band, sensor, target,
                 alpha=1.3, w=1.5, dT=10.0, lo=1e-17, hi=1e-11, n50=None):
    def h(log10_cn2):
        r = m.range_for_pd(_atmo_from(mor, alpha, w, 10.0 ** log10_cn2),
                           band, sensor, target, 0.5, n50=n50)
        if not np.isfinite(r):
            return R_target + 1.0
        return r - R_target
    lo_l, hi_l = np.log10(lo), np.log10(hi)
    if h(lo_l) < 0 or h(hi_l) > 0:
        return float("nan")
    x = brentq(h, lo_l, hi_l, xtol=1e-3)
    return float(10.0 ** x)


def critical_w(mor, R_target, band, sensor, target,
               alpha=1.3, cn2=1e-14, dT=10.0, lo=0.1, hi=8.0, n50=None):
    def g(w):
        r = m.range_for_pd(_atmo_from(mor, alpha, w, cn2), band, sensor, target,
                           0.5, n50=n50)
        if not np.isfinite(r):
            return -R_target
        return r - R_target
    if g(lo) < 0 or g(hi) > 0:
        return float("nan")
    return float(brentq(g, lo, hi, xtol=1e-3))


def critical_curves(sensor, target, R_target=8.0, band="LWIR", n50=2.0):
    alpha_grid = np.linspace(0.0, 1.6, 17)
    mor_grid = np.geomspace(0.6, 23.0, 16)
    rows = []
    for a in alpha_grid:
        rows.append(dict(kind="MOR_vs_alpha", x=a,
                         y=critical_mor(a, R_target, band, sensor, target, n50=n50)))
    for mor in mor_grid:
        rows.append(dict(kind="Cn2_vs_MOR", x=mor,
                         y=critical_cn2(mor, R_target, band, sensor, target, n50=n50)))
        rows.append(dict(kind="w_vs_MOR", x=mor,
                         y=critical_w(mor, R_target, band, sensor, target, n50=n50)))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 相图网格
# --------------------------------------------------------------------------- #
def phase_R50_grid(sensor, target, band, mor_grid, alpha_grid,
                   w=1.5, cn2=1e-14, dT=10.0, n50=None):
    Z = np.full((len(mor_grid), len(alpha_grid)), np.nan)
    for i, mor in enumerate(mor_grid):
        for j, a in enumerate(alpha_grid):
            Z[i, j] = m.range_for_pd(_atmo_from(mor, a, w, cn2), band, sensor, target,
                                     0.5, n50=n50)
    return Z


def phase_pd_grid(sensor, target, band, mor_grid, R_grid,
                  alpha=1.3, w=1.5, cn2=1e-14, dT=10.0, n50=None):
    n50 = sensor.n50 if n50 is None else n50
    Z = np.full((len(mor_grid), len(R_grid)), np.nan)
    for i, mor in enumerate(mor_grid):
        for j, R in enumerate(R_grid):
            ev = m.evaluate_at_range(_atmo_from(mor, alpha, w, cn2), band, R, sensor, target)
            Z[i, j] = m.pd_ttpf(ev["n"], n50, sensor.beta_ttpf)
    return Z


# --------------------------------------------------------------------------- #
# 天气因子两两组合矩阵（热力图集）
# --------------------------------------------------------------------------- #
WEATHER_GRIDS = {
    "MOR": np.geomspace(0.5, 23.0, 30),
    "alpha": np.linspace(0.0, 1.6, 18),
    "w": np.linspace(0.5, 5.0, 18),
    "Cn2": np.geomspace(1e-16, 1e-13, 22),
}
WEATHER_LABELS = {
    "MOR": "MOR (km)",
    "alpha": "Ångström α",
    "w": "可降水量 w (cm)",
    "Cn2": "Cn² (m^-2/3)",
}
NOMINAL = dict(MOR=5.0, alpha=1.3, w=1.5, Cn2=1e-14)
WEATHER_PAIRS = [("MOR", "alpha"), ("MOR", "w"), ("MOR", "Cn2"),
                 ("alpha", "w"), ("alpha", "Cn2"), ("w", "Cn2")]


def weather_pair_grid(pair, band, sensor, target, metric="Rdet", nominal=None):
    """固定其余两个天气参数，在 (x, y) 网格上计算 Rdet 或 R50。"""
    nom = dict(NOMINAL if nominal is None else nominal)
    xname, yname = pair
    X = WEATHER_GRIDS[xname]
    Y = WEATHER_GRIDS[yname]
    Z = np.full((len(X), len(Y)), np.nan)
    n50 = sensor.n50_detect if metric == "Rdet" else sensor.n50
    for i, x in enumerate(X):
        for j, y in enumerate(Y):
            vals = dict(nom)
            vals[xname] = x
            vals[yname] = y
            at = _atmo_from(vals["MOR"], vals["alpha"], vals["w"], vals["Cn2"])
            Z[i, j] = m.range_for_pd(at, band, sensor, target, 0.5, n50=n50, Rmax=40.0)
    return X, Y, Z

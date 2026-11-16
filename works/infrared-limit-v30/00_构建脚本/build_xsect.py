# -*- coding: utf-8 -*-
"""构建 HITRAN2020 吸收截面表：07_光谱数据/xsect_mwir.npz、xsect_lwir.npz

维度：温度 220/250/280/300 K × 气压 1.0/0.6/0.36/0.2 atm（H2O/CO2/CH4）；
      温度同上 × 气压 1.0 atm（O3/N2O/CO）。
键名：``<物种>_T<温度>_P<气压两位小数>``，如 ``CO2_T280_P0.60``；另有 ``nu``。

数据来源与物理
--------------
* H2O / CO2 / CH4：参考项目 ``F:\\DeepSeek工作区\\hitran_slant\\lines\\*.npz`` 中已解析的
  HITRAN2020 线表（键 iso, nu, sw, gair, gself, elower, nair, delta），用与该参考项目
  ``lbl.py`` 相同的逐线物理（Voigt via scipy.special.wofz、TIPS 配分函数
  hapi.partitionSum、气压频移、线强温度修正、线翼 25/12/6 cm⁻¹ 截断、弱线粗网格加速）。
  唯一修正是：HITRAN 的 sw 已含天然同位素丰度（HAPI 表头原文 "Line intensity,
  multiplied by isotopologue abundance"），故不再额外乘丰度（参考项目在此处多乘了一次，
  会使 13CO2 等次丰度同位素谱线偏弱约 1/丰度倍）。
* O3 / N2O / CO：由 ``_download/fetch_hitran_lines.py`` 从 HITRANonline /lbl/api 下载的
  HITRAN2020 原始定宽线表，装配为 HAPI 数据库表后用
  ``hapi.absorptionCoefficient_Voigt`` 计算（Diluent={"air":1}，HITRAN_units=True），
  同样覆盖 4 气压 × 4 温度节点（CO 在 2375–2875 cm⁻¹ 无 HITRAN 数据，HITRANonline
  返回 404，该区间按空处理；CO 的 1-0 带在 2000–2300 cm⁻¹ 范围内不受影响）。

气压节点含义：P 为相对标准大气压（1013.25 hPa）的倍数，与大气廓线中
``p_atm = p_hPa/1013.25`` 一致；层气压在 0.2–1.0 之间，用对数气压线性插值。

用法
----
    python build_xsect.py --phase lbl --procs 6     # H2O/CO2/CH4 多气压多温度
    python build_xsect.py --phase hapi --procs 4    # O3/N2O/CO（1 atm）
    python build_xsect.py --phase all --procs 6

输出（每个波段一个 npz，包含该波段全物种全节点）
"""
import os
import sys
import json
import time
import argparse
import io
import contextlib
import multiprocessing as mp

import numpy as np
from scipy.special import wofz

import hapi

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_DIR = os.path.join(BASE_DIR, "07_光谱数据")
HAPI_RAW = os.path.join(SPEC_DIR, "_hapi_db", "raw")
HAPI_TABLES = os.path.join(SPEC_DIR, "_hapi_db", "tables")
LINES_DIR = r"F:\DeepSeek工作区\hitran_slant\lines"

BAND_GRID = {"MWIR": (2000.0, 4000.0), "LWIR": (775.0, 1360.0)}
STEP_CM = 0.05
TEMPS_K = (220.0, 250.0, 280.0, 300.0)
PRESSURES_ATM = (1.0, 0.60, 0.36, 0.20)
LBL_SPECIES = ("H2O", "CO2", "CH4")
HAPI_SPECIES = ("O3", "N2O", "CO")
HAPI_MOL = {"O3": 3, "N2O": 4, "CO": 5}
ALL_SPECIES = ("H2O", "CO2", "O3", "N2O", "CO", "CH4")

# 物理常数（与参考项目 lbl.py 一致）
C2 = 1.438776877          # hc/k  [cm·K]
KB = 1.380649e-23         # J/K
C_CM = 2.99792458e10      # cm/s
AMU = 1.66053906660e-27   # kg
SQPI = np.sqrt(np.pi)
T_REF = 296.0
WING_STRONG, WING_MED, WING_WEAK = 25.0, 12.0, 6.0
S_STRONG, S_MED, S_MIN = 1.0e-22, 1.0e-25, 1.0e-28
COARSE_FACTOR, S_COARSE = 5, 3.0e-25


# --------------------------------------------------------------------------- #
# 逐线物理（与参考项目 hitran_slant/lbl.py 同款，修正同位素丰度重复折算）
# --------------------------------------------------------------------------- #
class Lines:
    """单一分子的 HITRAN2020 线参数（全部同位素，sw 已含天然丰度）。"""

    def __init__(self, path, molecule_id, iso_table, partition_sum):
        d = np.load(path)
        iso = np.asarray(d["iso"], dtype=int)
        nu, sw = np.asarray(d["nu"], float), np.asarray(d["sw"], float)
        gair, gself = np.asarray(d["gair"], float), np.asarray(d["gself"], float)
        elower, nair, delta = (np.asarray(d["elower"], float),
                               np.asarray(d["nair"], float),
                               np.asarray(d["delta"], float))
        keep = (sw >= S_MIN) & np.isfinite(nu) & np.isfinite(sw) & (iso >= 1)
        iso, nu, sw = iso[keep], nu[keep], sw[keep]
        gair, gself = gair[keep], gself[keep]
        elower, nair, delta = elower[keep], nair[keep], delta[keep]

        self.M = molecule_id
        self.iso, self.nu, self.sw = iso, nu, sw
        self.gair = np.maximum(gair, 1.0e-4)
        self.gself = np.maximum(gself, 1.0e-4)
        self.elower, self.nair, self.delta = elower, nair, delta

        uniq = np.unique(iso)
        self.iso_uniq = uniq
        self.iso_map = np.searchsorted(uniq, iso)
        self.abund = np.array([iso_table[(molecule_id, i)][2] for i in uniq])[self.iso_map]
        self.mass = np.array([iso_table[(molecule_id, i)][3]
                              for i in uniq])[self.iso_map] * AMU
        self.q296 = np.array([partition_sum(molecule_id, i, T_REF)
                              for i in uniq])[self.iso_map]
        self.half = np.where(sw >= S_STRONG, WING_STRONG,
                             np.where(sw >= S_MED, WING_MED, WING_WEAK))
        self.coarse = sw < S_COARSE

    def sigma(self, T, p_atm, grid, step, qT_iso, x_self=0.0):
        """吸收截面 cm²/molecule；p_atm 以标准大气压为单位，x_self=0 为纯空气加宽。"""
        ng = grid.size
        sigma = np.zeros(ng)
        qT = qT_iso[self.iso_map]

        boltz = np.exp(-C2 * self.elower * (1.0 / T - 1.0 / T_REF))
        stim = ((1.0 - np.exp(-C2 * self.nu / T))
                / (1.0 - np.exp(-C2 * self.nu / T_REF)))
        sT = self.sw * (self.q296 / qT) * boltz * stim

        p_self = p_atm * x_self
        gl = ((T_REF / T) ** self.nair
              * (self.gair * (p_atm - p_self) + self.gself * p_self))
        gl = np.maximum(gl, 1.0e-8)
        gd = (self.nu / C_CM) * np.sqrt(2.0 * KB * T / self.mass)
        gd = np.maximum(gd, 1.0e-10)
        nus = self.nu + self.delta * p_atm

        sel = (nus + self.half > grid[0]) & (nus - self.half < grid[-1])
        if not sel.all():
            nus, gl, gd, sT = nus[sel], gl[sel], gd[sel], sT[sel]
            half, coarse = self.half[sel], self.coarse[sel]
        else:
            half, coarse = self.half, self.coarse

        g0 = grid[0]
        for i in range(nus.size):
            c = nus[i]
            lo = int((c - half[i] - g0) / step)
            hi = int((c + half[i] - g0) / step) + 2
            if lo < 0:
                lo = 0
            if hi > ng:
                hi = ng
            if hi <= lo:
                continue
            y = gl[i] / gd[i]
            if coarse[i]:
                xs = grid[slice(lo, hi, COARSE_FACTOR)]
                f = wofz((xs - c) / gd[i] + 1j * y).real * (1.0 / (gd[i] * SQPI))
                sig = np.interp(grid[lo:hi], xs, f)
                sigma[lo:hi] += sT[i] * sig
            else:
                f = wofz((grid[lo:hi] - c) / gd[i] + 1j * y).real * (1.0 / (gd[i] * SQPI))
                sigma[lo:hi] += sT[i] * f
        return np.maximum(sigma, 0.0)


# --------------------------------------------------------------------------- #
# HAPI 数据库表装配（O3 / N2O / CO）
# --------------------------------------------------------------------------- #
_HEADER_TEMPLATE = {
    "number_of_rows": -1,
    "format": {
        "a": "%10.3E", "gamma_air": "%5.4f", "gp": "%7.1f",
        "local_iso_id": "%1d", "molec_id": "%2d", "sw": "%10.3E",
        "local_lower_quanta": "%15s", "local_upper_quanta": "%15s",
        "gpp": "%7.1f", "elower": "%10.4f", "n_air": "%4.2f",
        "delta_air": "%8.6f", "global_upper_quanta": "%15s",
        "global_lower_quanta": "%15s", "iref": "%12s",
        "line_mixing_flag": "%1s", "ierr": "%6s", "nu": "%12.6f",
        "gamma_self": "%5.3f",
    },
    "default": {
        "a": 0.0, "gamma_air": 0.0, "gp": "FFF", "local_iso_id": 0,
        "molec_id": 0, "sw": 0.0, "local_lower_quanta": "000",
        "local_upper_quanta": "000", "gpp": "FFF", "elower": 0.0,
        "n_air": 0.0, "delta_air": 0.0, "global_upper_quanta": "000",
        "global_lower_quanta": "000", "iref": "EEE", "line_mixing_flag": "EEE",
        "ierr": "EEE", "nu": 0.0, "gamma_self": 0.0,
    },
    "table_type": "column-fixed",
    "order": ["molec_id", "local_iso_id", "nu", "sw", "a", "gamma_air",
              "gamma_self", "elower", "n_air", "delta_air", "global_upper_quanta",
              "global_lower_quanta", "local_upper_quanta", "local_lower_quanta",
              "ierr", "iref", "line_mixing_flag", "gp", "gpp"],
    "position": {"molec_id": 0, "local_iso_id": 2, "nu": 3, "sw": 15, "a": 25,
                 "gamma_air": 35, "gamma_self": 40, "elower": 45, "n_air": 55,
                 "delta_air": 59, "global_upper_quanta": 67,
                 "global_lower_quanta": 82, "local_upper_quanta": 97,
                 "local_lower_quanta": 112, "ierr": 127, "iref": 133,
                 "line_mixing_flag": 145, "gp": 146, "gpp": 153},
    "extra": [], "extra_format": {}, "extra_separator": ",",
    "size_in_bytes": -1,
}


def assemble_hapi_table(species, out_dir):
    """把 ``_hapi_db/raw/<species>_*.par`` 装配成一个 HAPI 表；返回 (表名, 行数, 覆盖范围)。"""
    mol = HAPI_MOL[species]
    files = sorted(f for f in os.listdir(HAPI_RAW)
                   if f.startswith(species + "_") and f.endswith(".par"))
    if not files:
        return None, 0, (np.nan, np.nan)
    seen = set()
    rows = []
    nraw = 0
    for f in files:
        with open(os.path.join(HAPI_RAW, f), "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if len(line) < 67:
                    continue
                try:
                    m = int(line[0:2])
                    iso = int(line[2:3])
                    nu = float(line[3:15])
                    swv = float(line[15:25])
                except ValueError:
                    continue
                if m != mol:
                    continue
                nraw += 1
                key = (iso, round(nu, 6), swv)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(line.ljust(160))
    if not rows:
        return None, 0, (np.nan, np.nan)
    rows.sort(key=lambda s: float(s[3:15]))
    os.makedirs(out_dir, exist_ok=True)
    table = species + "_hitran2020"
    with open(os.path.join(out_dir, table + ".data"), "w",
              encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(r + "\n")
    header = dict(_HEADER_TEMPLATE)
    header["table_name"] = table
    header["number_of_rows"] = len(rows)
    header["size_in_bytes"] = os.path.getsize(os.path.join(out_dir, table + ".data"))
    header["comment"] = ("HITRAN2020 lines for %s, assembled from HITRANonline /lbl/api "
                         "raw .par chunks (%d rows after de-dup of %d raw rows)."
                         % (species, len(rows), nraw))
    with open(os.path.join(out_dir, table + ".header"), "w", encoding="utf-8") as f:
        json.dump(header, f, ensure_ascii=False, indent=2)
    nus = [float(r[3:15]) for r in rows]
    return table, len(rows), (min(nus), max(nus))


_HAPI_COEF_CACHE = {}


def _hapi_sigma(species, T, P, lo, hi, table):
    """用 HAPI 计算一个物种/温度/气压在波段网格上的截面（进程内缓存表）。"""
    mol = HAPI_MOL[species]
    if table not in hapi.LOCAL_TABLE_CACHE:
        with contextlib.redirect_stdout(io.StringIO()):
            hapi.db_begin(HAPI_TABLES)
    iso_list = [i for (m, i) in sorted(hapi.ISO) if m == mol]
    nu = np.arange(lo, hi + STEP_CM * 0.5, STEP_CM)
    with contextlib.redirect_stdout(io.StringIO()):
        nu_h, coef = hapi.absorptionCoefficient_Voigt(
            Components=[(mol, i) for i in iso_list],
            SourceTables=[table],
            WavenumberRange=[lo, hi], WavenumberStep=STEP_CM,
            Environment={"p": float(P), "T": float(T)},
            HITRAN_units=True, Diluent={"air": 1.0})
    nu_h = np.asarray(nu_h, float)
    coef = np.asarray(coef, float)
    if nu_h.size != nu.size:
        coef = np.interp(nu, nu_h, coef)
    return np.maximum(coef, 0.0)


# --------------------------------------------------------------------------- #
# 任务
# --------------------------------------------------------------------------- #
_HAPI_TABLES = {}


def work(task):
    """(engine, species, band, T, P) → (species, band, T, P, coef, engine)"""
    engine, species, band, T, P = task
    lo, hi = BAND_GRID[band]
    grid = np.arange(lo, hi + STEP_CM * 0.5, STEP_CM)
    t0 = time.time()
    if engine == "hapi":
        table = _HAPI_TABLES.get(species) or (species + "_hitran2020")
        coef = _hapi_sigma(species, T, P, lo, hi, table)
    else:
        path = os.path.join(LINES_DIR, species + ".npz")
        mol = {"H2O": 1, "CO2": 2, "CH4": 6}[species]
        L = Lines(path, mol, hapi.ISO, hapi.partitionSum)
        qT = np.array([hapi.partitionSum(mol, i, T) for i in L.iso_uniq])
        coef = L.sigma(T, P, grid, STEP_CM, qT)
    return species, band, T, P, coef.astype(np.float32), engine, time.time() - t0


# --------------------------------------------------------------------------- #
# npz 写入 + 自检
# --------------------------------------------------------------------------- #
def npz_path(band):
    return os.path.join(SPEC_DIR, "xsect_%s.npz" % band.lower())


def write_npz(band, data, engines, hapi_tables):
    """data: {(species,T,P): array}；写 npz + meta + 自检。"""
    lo, hi = BAND_GRID[band]
    nu = np.arange(lo, hi + STEP_CM * 0.5, STEP_CM)
    arrays = {}
    for (sp, T, P), arr in data.items():
        arrays["%s_T%d_P%.2f" % (sp, int(T), P)] = np.asarray(arr, np.float32)
    have = sorted({k.split("_T")[0] for k in arrays})
    missing = [s for s in ALL_SPECIES if s not in have]
    nodes = {}
    for sp in have:
        nodes[sp] = sorted({float(k.split("_P")[-1]) for k in arrays
                            if k.startswith(sp + "_T")})
    meta = dict(
        source="HITRAN2020 逐线 Voigt 吸收截面（HITRANonline /lbl/api + 参考项目已解析线表）",
        generator="00_构建脚本/build_xsect.py",
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        hitran="HITRAN2020（Gordon et al. 2022）",
        line_shape="Voigt（含气压频移与线强温度修正，线翼 25/12/6 cm⁻¹ 截断）",
        units="cm^2/molecule",
        pressure_unit="atm（= 1013.25 hPa；与大气层 p_atm 同口径）",
        temperatures_K=list(TEMPS_K),
        pressures_atm=list(PRESSURES_ATM),
        species_pressure_nodes=nodes,
        engines=engines,
        hapi_tables=hapi_tables,
        species=have,
        missing=missing,
        grid=dict(nu_min=float(nu[0]), nu_max=float(nu[-1]), step=STEP_CM,
                  n=int(nu.size), ascending=True, unit="cm^-1"),
        notes=("H2O/CO2/CH4：参考项目 hitran_slant/lines 的 HITRAN2020 线表 + 与 lbl.py "
               "相同的逐线物理（修正其丰度重复折算）；O3/N2O/CO：HITRANonline 原始线表 + "
               "HAPI 1.3 absorptionCoefficient_Voigt；6 物种均含 4 温度 × 4 气压节点。"
               "不含水汽连续吸收（MT_CKD）与散射。"),
    )
    header = ("HITRAN2020 Voigt absorption cross sections | %s: %.2f–%.2f cm⁻¹ step %.2f | "
              "T=220/250/280/300 K, P=1.0/0.6/0.36/0.2 atm (H2O/CO2/CH4); "
              "O3/N2O/CO @1 atm | cm²/molecule" % (band, nu[0], nu[-1], STEP_CM))
    np.savez_compressed(npz_path(band), nu=nu.astype(np.float64), **arrays,
                        header=np.array(header),
                        meta=np.array(json.dumps(meta, ensure_ascii=False)),
                        missing=np.array(",".join(missing)),
                        complete=np.array("true" if not missing else "false"))
    # ---- 自检 ----
    with np.load(npz_path(band), allow_pickle=False) as d:
        nn = d["nu"].size
        for k in d.files:
            if k in ("header", "meta", "missing", "complete", "nu"):
                continue
            a = np.asarray(d[k], float)
            assert a.shape == (nn,), "键 %s 形状 %s 与 nu %d 不一致" % (k, a.shape, nn)
            assert np.all(np.isfinite(a)), "键 %s 含 NaN/Inf" % k
            assert a.min() >= 0.0, "键 %s 含负值" % k
        assert np.all(np.diff(d["nu"]) > 0), "nu 非升序"
    return missing, len(arrays), nodes


def load_existing(band):
    """载入已有 npz 的截面键（供分阶段运行合并）。"""
    path = npz_path(band)
    data = {}
    if not os.path.exists(path):
        return data
    with np.load(path, allow_pickle=False) as d:
        for k in d.files:
            if not (k.startswith(tuple(ALL_SPECIES)) and "_T" in k):
                continue
            sp = k.split("_T")[0]
            rest = k.split("_T")[1]
            T = float(rest.split("_P")[0])
            P = float(rest.split("_P")[1]) if "_P" in rest else 1.0
            data[(sp, T, P)] = np.asarray(d[k], dtype=np.float32)
    return data


def load_meta(band):
    path = npz_path(band)
    if not os.path.exists(path):
        return {}
    with np.load(path, allow_pickle=False) as d:
        if "meta" in d.files:
            try:
                return json.loads(str(d["meta"]))
            except Exception:
                return {}
    return {}


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["lbl", "hapi", "all"])
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--band", default="both", choices=["both", "mwir", "lwir"])
    args = ap.parse_args()
    bands = ["MWIR", "LWIR"] if args.band == "both" else [args.band.upper()]

    os.makedirs(HAPI_TABLES, exist_ok=True)
    t_start = time.time()
    engines = {}
    hapi_tables = {}

    # 已有结果（合并用）
    data = {band: load_existing(band) for band in bands}
    prev_meta = {band: load_meta(band) for band in bands}
    for band in bands:
        engines.update(prev_meta[band].get("engines", {}))
        hapi_tables.update(prev_meta[band].get("hapi_tables", {}))

    # ---------------- 阶段 1：H2O/CO2/CH4（多气压 × 多温度）----------------
    if args.phase in ("lbl", "all"):
        tasks = [("lbl", sp, band, T, P)
                 for band in bands for sp in LBL_SPECIES
                 for T in TEMPS_K for P in PRESSURES_ATM]
        print("[plan-lbl] %d 个任务（3 物种 × 2 波段 × 4 温度 × 4 气压），%d 进程"
              % (len(tasks), args.procs), flush=True)
        n = 0
        with mp.Pool(args.procs) as pool:
            for sp, band, T, P, coef, engine, sec in pool.imap_unordered(work, tasks):
                data[band][(sp, T, P)] = coef
                engines[sp] = engine
                n += 1
                print("[progress %d/%d] %s %s T=%dK P=%.2f  max=%.3e  %.1fs  (%.0fs)"
                      % (n, len(tasks), sp, band, int(T), P, float(coef.max()),
                         sec, time.time() - t_start), flush=True)
        for band in bands:
            missing, nkeys, nodes = write_npz(band, data[band], engines, hapi_tables)
            print("[write] %s: %d 键，缺失=%s，气压节点=%s → %s"
                  % (band, nkeys, missing or "无",
                     {k: v for k, v in nodes.items() if k in LBL_SPECIES},
                     npz_path(band)), flush=True)

    # ---------------- 阶段 2：O3/N2O/CO（1 atm × 多温度）----------------
    if args.phase in ("hapi", "all"):
        for sp in HAPI_SPECIES:
            t0 = time.time()
            table, nrows, rng = assemble_hapi_table(sp, HAPI_TABLES)
            if table is None:
                print("[assemble] %s: 无原始线表（missing）" % sp, flush=True)
                continue
            hapi_tables[sp] = dict(table=table, n_lines=int(nrows),
                                   nu_range=[float(rng[0]), float(rng[1])])
            print("[assemble] %s: %d 行，ν=%.1f–%.1f cm⁻¹ (%.1fs)"
                  % (sp, nrows, rng[0], rng[1], time.time() - t0), flush=True)
        tasks = [("hapi", sp, band, T, P)
                 for band in bands for sp in HAPI_SPECIES
                 if sp in hapi_tables for T in TEMPS_K for P in PRESSURES_ATM]
        print("[plan-hapi] %d 个任务（3 物种 × 2 波段 × 4 温度 × 4 气压），%d 进程"
              % (len(tasks), min(6, args.procs)), flush=True)
        n = 0
        with mp.Pool(min(6, args.procs)) as pool:
            for sp, band, T, P, coef, engine, sec in pool.imap_unordered(work, tasks):
                data[band][(sp, T, P)] = coef
                engines[sp] = engine
                n += 1
                print("[progress %d/%d] %s %s T=%dK P=%.2f  max=%.3e  %.0fs  (%.0fs)"
                      % (n, len(tasks), sp, band, int(T), P, float(coef.max()),
                         sec, time.time() - t_start), flush=True)
        for band in bands:
            missing, nkeys, nodes = write_npz(band, data[band], engines, hapi_tables)
            print("[write] %s: %d 键，缺失=%s，气压节点=%s → %s"
                  % (band, nkeys, missing or "无",
                     {k: v for k, v in nodes.items()}, npz_path(band)), flush=True)

    print("[done] 总计 %.0fs" % (time.time() - t_start), flush=True)


if __name__ == "__main__":
    main()

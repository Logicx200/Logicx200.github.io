# -*- coding: utf-8 -*-
"""V3.0 光谱大气：HITRAN / HAPI 逐线 Voigt 吸收系数生产线（T1 负责）。

口径（与 00_构建脚本/接口约定.md §1 一致）：
  * 波段  MWIR: 2000–4000 cm⁻¹（2.5–5.0 μm）
          LWIR:  800–1333 cm⁻¹（7.5–12.51 μm）
  * 物种  H2O(1,1) / CO2(2,1) / O3(3,1) / N2O(4,1) / CO(5,1) / CH4(6,1)
  * 温度  250 / 280 / 300 K（P = 1.01325 atm，Diluent = air，步长 0.05 cm⁻¹）
  * 线型  absorptionCoefficient_Voigt，HITRAN_units=True（cm²/molecule）
  * 表外延 抓取时在计算区间两端各外延 FETCH_PAD=25 cm⁻¹ 仅补线翼。

输出（全部落在 07_光谱数据/，本脚本不写其它任何目录）：
  xsect_mwir.npz / xsect_lwir.npz
      键：nu                    float64 (N,)  cm⁻¹ 升序
          H2O_T250 ... CH4_T300 float32 (N,)  cm²/molecule
          （缺失物种**不写键**，另见 header / meta / missing / complete）
      header : 文件内说明（键名、单位、口径）  meta : JSON 元数据
      missing: 逗号分隔缺失物种               complete: 该波段是否齐全
  _hapi_db/                  HAPI 行数据库（.data/.header，断点续跑复用）
  _xsect_parts/              单 (band,species,T) 中间 .npy 缓存（断点续跑）
  _fetch_status*.json        各步骤状态、耗时、失败原因

提速策略（重要）：
  * 每完成一个物种的 3 个温度就**增量重写**该波段 npz —— 下游链路可立即使用，
    不必等全部物种；后续运行会覆盖为更全版本。
  * 支持 `--bands mwir` / `--bands lwir` 拆成两个进程并行抓取/计算。
  * 物种按优先级顺序：P0 (MWIR: H2O CO2 CH4 / LWIR: H2O CO2 O3)，P1 其余。

稳健性：
  * 每个 (物种,温度) 独立重试，最多 3 次，指数退避 2/4 s；
  * 已有 .data/.header 缓存直接复用，不重抓；
  * 单物种彻底失败不终止整体，跳过即可（npz 中不写该键）；
  * 总耗时超过 --time-budget-min（默认 40）时落盘已完成部分后退出码 2，
    下次运行从缓存续跑。

运行示例：
  python -u 00_构建脚本/fetch_hitran_all.py --bands mwir
  python -u 00_构建脚本/fetch_hitran_all.py --bands lwir --status-suffix _lwir
  python -u 00_构建脚本/fetch_hitran_all.py            # 两波段串行
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

import hapi

# Windows GBK 控制台无法编码上标/勾选符号，统一做容错替换，避免刷屏时崩溃
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------- 路径与口径
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # 红外识别极限重构_V3.0
OUTDIR = os.path.join(ROOT, "07_光谱数据")
DBDIR = os.path.join(OUTDIR, "_hapi_db")
PARTDIR = os.path.join(OUTDIR, "_xsect_parts")
os.makedirs(DBDIR, exist_ok=True)
os.makedirs(PARTDIR, exist_ok=True)

BANDS = {
    "mwir": (2000.0, 4000.0),                     # cm⁻¹
    "lwir": (800.0, 1333.0),                      # cm⁻¹
}
SPECIES = {
    "H2O": (1, 1),
    "CO2": (2, 1),
    "O3": (3, 1),
    "N2O": (4, 1),
    "CO": (5, 1),
    "CH4": (6, 1),
}
# 优先级：先保证下游“能用”（Lead P0），P1 随后补
PRIORITY = {
    "mwir": ("H2O", "CO2", "CH4", "O3", "N2O", "CO"),
    "lwir": ("H2O", "CO2", "O3", "CH4", "N2O", "CO"),
}
TEMPS = (250, 280, 300)
P_ATM = 1.01325
STEP_CM = 0.05
FETCH_PAD = 25.0                                  # cm⁻¹，只补线翼，不进输出网格
MAX_RETRY = 3
MIN_DATA_BYTES = 1000
NAMED_BAND = {"mwir": "MWIR", "lwir": "LWIR"}

_wall0 = time.time()


def log(msg: str) -> None:
    print("[%7.1fs] %s" % (time.time() - _wall0, msg), flush=True)


# ---------------------------------------------------------------- HAPI 会话
hapi.db_begin(DBDIR)


def table_name(band: str, name: str) -> str:
    wmin, wmax = BANDS[band]
    return "%s_%d_%d" % (name, int(wmin), int(wmax))


def data_path(table: str) -> str:
    return os.path.join(DBDIR, table + ".data")


def table_cached(table: str) -> bool:
    p = data_path(table)
    return os.path.exists(p) and os.path.getsize(p) >= MIN_DATA_BYTES


def ensure_table(band: str, name: str, M: int, I: int) -> str:
    """返回已载入 HAPI 缓存的行表名；必要时从 HITRAN online 抓取。"""
    table = table_name(band, name)
    if table in hapi.LOCAL_TABLE_CACHE:
        return table
    if table_cached(table):
        log("  复用本地行表 %s" % table)
        try:
            hapi.storage2cache(table)
            return table
        except Exception as exc:                  # 缓存损坏 -> 重抓
            log("  本地行表载入失败(%s)，重抓: %r" % (table, exc))
    wmin, wmax = BANDS[band]
    lo, hi = wmin - FETCH_PAD, wmax + FETCH_PAD
    log("  抓取 HITRAN %s(%d,%d) %.1f–%.1f cm⁻¹ ..." % (name, M, I, lo, hi))
    t = time.time()
    hapi.fetch(table, M, I, lo, hi)
    if not table_cached(table):
        raise RuntimeError("fetch 后本地行表缺失或过小: %s" % data_path(table))
    nrow = hapi.LOCAL_TABLE_CACHE[table]["header"].get("number_of_rows", "?")
    log("  抓取完成 %s  lines=%s  %.1fs" % (table, nrow, time.time() - t))
    return table


def unload_table(table: str) -> None:
    try:
        hapi.LOCAL_TABLE_CACHE.pop(table, None)
    except Exception:
        pass


# ---------------------------------------------------------------- 重试包装
def with_retry(fn, what: str):
    last = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return fn()
        except Exception as exc:                  # noqa: BLE001 - 兜住一切
            last = exc
            log("  [重试 %d/%d] %s 失败: %s: %s"
                % (attempt, MAX_RETRY, what, type(exc).__name__, exc))
            if attempt < MAX_RETRY:
                time.sleep(2.0 ** (attempt - 1) * 2.0)   # 2 s, 4 s
    raise RuntimeError("%s 连续 %d 次失败，最后一次: %r" % (what, MAX_RETRY, last))


# ---------------------------------------------------------------- 单块计算
def part_path(band: str, name: str, T: int) -> str:
    return os.path.join(PARTDIR, "%s__%s__T%d.npy" % (band, name, T))


def nu_path(band: str) -> str:
    return os.path.join(PARTDIR, "__nu__%s.npy" % band)


def load_part_if_ok(band: str, name: str, T: int):
    pf = part_path(band, name, T)
    if os.path.exists(pf) and os.path.getsize(pf) > 100:
        arr = np.load(pf)
        if arr.ndim == 1 and arr.size > 100 and np.all(np.isfinite(arr)):
            return np.asarray(arr, dtype=np.float64)
    return None


def compute_part(band: str, name: str, M: int, I: int, T: int) -> np.ndarray:
    """计算/读取单 (band, species, T) 截面，返回 cm²/molecule。"""
    cached = load_part_if_ok(band, name, T)
    if cached is not None:
        return cached

    wmin, wmax = BANDS[band]
    table = ensure_table(band, name, M, I)

    def _calc():
        nu, xs = hapi.absorptionCoefficient_Voigt(
            Components=[(M, I)],
            SourceTables=[table],
            Environment={"p": P_ATM, "T": float(T)},
            WavenumberRange=[wmin, wmax],
            WavenumberStep=STEP_CM,
            HITRAN_units=True,
            Diluent={"air": 1},
        )
        arr = np.asarray(xs, dtype=np.float64)
        if arr.ndim != 1 or arr.size < 100:
            raise RuntimeError("输出维度异常: %r" % (arr.shape,))
        if not np.all(np.isfinite(arr)):
            raise RuntimeError("输出含非有限值")
        if float(np.min(arr)) < 0.0:
            raise RuntimeError("输出含负截面")
        nu = np.asarray(nu, dtype=np.float64)
        nuf = nu_path(band)
        if os.path.exists(nuf):
            nu0 = np.load(nuf)
            if nu0.shape != nu.shape or not np.allclose(nu0, nu, rtol=0, atol=1e-6):
                raise RuntimeError("nu 网格与已缓存不一致")
        else:
            np.save(nuf, nu)
        return arr

    t = time.time()
    arr = with_retry(_calc, "%s %s T=%dK" % (NAMED_BAND[band], name, T))
    np.save(part_path(band, name, T), arr.astype(np.float32))
    log("  ✓ %s %s T=%dK  n=%d  max=%.4e cm²/molec  %.1fs"
        % (NAMED_BAND[band], name, T, arr.size, float(arr.max()), time.time() - t))
    return arr


# ---------------------------------------------------------------- 落盘
HEADER_TMPL = """V3.0 光谱大气 HITRAN 逐线 Voigt 吸收系数（HAPI {hapi_ver}）
band       : {band}   {wmin:.1f}-{wmax:.1f} cm-1   ({lam_lo:.2f}-{lam_hi:.2f} um)
grid       : nu 升序，步长 {step:.2f} cm-1，N={n}
species    : HITRAN2020 line list，H2O(1,1) CO2(2,1) O3(3,1) N2O(4,1) CO(5,1) CH4(6,1)
conditions : T = 250/280/300 K, P = {p:.5f} atm, Diluent=air, line shape=Voigt, HITRAN_units=True
units      : nu -> cm-1 ; <species>_T<temp> -> cm^2/molecule (cross-section)
key format : nu, H2O_T250, H2O_T280, H2O_T300, CO2_T250, ...
note       : 抓取区间两端各外延 {pad:.0f} cm-1 补线翼；输出网格严格裁到 [wmin,wmax]
            缺失物种不写键（见 missing / complete / meta）
available  : {avail}
missing    : {missing}
complete   : {complete}
generated  : {ts}
"""


def assemble_band(band: str, missing=None, time_up=False) -> bool:
    """把当前已完成 part 组装为 xsect_<band>.npz；缺失物种不写键。

    每完成一个物种即调用一次，保证下游尽早可用；后续调用覆盖为更全版本。
    """
    missing = list(missing or [])
    nuf = nu_path(band)
    if not os.path.exists(nuf):
        return False
    nu = np.load(nuf)
    wmin, wmax = BANDS[band]
    payload = {"nu": np.asarray(nu, dtype=np.float64)}
    avail, missing = [], []
    for name in PRIORITY[band] + tuple(s for s in SPECIES if s not in PRIORITY[band]):
        has_all = True
        for T in TEMPS:
            arr = load_part_if_ok(band, name, T)
            if arr is None or arr.shape != nu.shape:
                has_all = False
                break
        if not has_all:
            missing.append(name)
            continue
        for T in TEMPS:
            payload["%s_T%d" % (name, T)] = load_part_if_ok(
                band, name, T).astype(np.float32)
        avail.append(name)
    if not avail:
        log("✗ %s: 还没有任何完整物种，暂不落盘" % NAMED_BAND[band])
        return False
    complete = len(avail) == len(SPECIES)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    header = HEADER_TMPL.format(
        hapi_ver=getattr(hapi, "HAPI_VERSION", "1.3.0.0"),
        band=NAMED_BAND[band], wmin=wmin, wmax=wmax,
        lam_lo=1e4 / wmax, lam_hi=1e4 / wmin,
        step=STEP_CM, n=nu.size, p=P_ATM, pad=FETCH_PAD,
        avail=",".join(avail), missing=",".join(missing) if missing else "none",
        complete=bool(complete), ts=ts,
    )
    meta = {
        "band": NAMED_BAND[band],
        "wavenumber_range_cm1": [wmin, wmax],
        "wavelength_range_um": [1e4 / wmax, 1e4 / wmin],
        "step_cm1": STEP_CM,
        "n_points": int(nu.size),
        "temps_K": list(TEMPS),
        "pressure_atm": P_ATM,
        "species_available": avail,
        "missing_species": missing,
        "line_list": "HITRAN2020",
        "hapi_version": getattr(hapi, "HAPI_VERSION", "1.3.0.0"),
        "cross_section_units": "cm^2/molecule",
        "key_format": "<species>_T<temp>",
        "fetch_pad_cm1": FETCH_PAD,
        "complete": bool(complete),
        "time_budget_exceeded": bool(time_up),
        "generated": ts,
    }
    payload["header"] = np.array(header)
    payload["meta"] = np.array(json.dumps(meta, ensure_ascii=False))
    payload["missing"] = np.array(",".join(missing))
    payload["complete"] = np.array(bool(complete))
    out = os.path.join(OUTDIR, "xsect_%s.npz" % band)
    tmp = out + ".tmp.npz"
    np.savez_compressed(tmp, **payload)
    os.replace(tmp, out)
    log("落盘 %s  (%.2f MB, complete=%s, avail=%s)"
        % (out, os.path.getsize(out) / 1e6, complete, ",".join(avail)))
    return complete


def band_species_done(band: str, name: str) -> bool:
    return all(load_part_if_ok(band, name, T) is not None for T in TEMPS)


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="HITRAN HAPI 双波段吸收系数生产线")
    ap.add_argument("--bands", default="mwir,lwir",
                    help="要处理哪些波段：mwir,lwir 的组合，默认两者串行")
    ap.add_argument("--status-suffix", default="",
                    help="状态文件名后缀（并行进程用，避免互相覆盖）")
    ap.add_argument("--time-budget-min", type=float, default=40.0,
                    help="总耗时预算（分钟），超时落盘已完成部分后退出码 2")
    args = ap.parse_args()
    bands = [b.strip().lower() for b in args.bands.split(",") if b.strip()]
    for b in bands:
        if b not in BANDS:
            raise SystemExit("未知波段 %r" % b)
    budget_s = max(1.0, args.time_budget_min) * 60.0
    status_path = os.path.join(OUTDIR, "_fetch_status%s.json" % args.status_suffix)

    status = {
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "bands_requested": bands,
        "hapi_version": getattr(hapi, "HAPI_VERSION", "1.3.0.0"),
        "bands": {},
        "time_budget_s": budget_s,
    }
    failed_species = set()
    time_up = False
    all_complete = True

    for band in bands:
        bstat = {"parts": {}, "complete": False, "elapsed_s": None}
        status["bands"][band] = bstat
        t_band = time.time()
        log("=" * 78)
        log("波段 %s : %.1f–%.1f cm⁻¹  (优先级 %s)"
            % (NAMED_BAND[band], *BANDS[band], " > ".join(PRIORITY[band])))
        for name in PRIORITY[band]:
            M, I = SPECIES[name]
            # 已完整缓存的物种直接跳过
            if band_species_done(band, name):
                log("= %s %s 三温度已缓存，跳过计算" % (NAMED_BAND[band], name))
                bstat["parts"][name] = "cached"
                assemble_band(band)
                continue
            log("-- 物种 %s (%d,%d) --" % (name, M, I))
            for T in TEMPS:
                if load_part_if_ok(band, name, T) is not None:
                    log("  = %s %s T=%dK 已缓存" % (NAMED_BAND[band], name, T))
                    bstat["parts"]["%s_T%d" % (name, T)] = "cached"
                    continue
                elapsed = time.time() - _wall0
                if elapsed > budget_s:
                    time_up = True
                    log("⏱ 总耗时 %.0fs 已超 %.0fs 预算：停止新计算，落盘已完成部分"
                        % (elapsed, budget_s))
                    break
                t = time.time()
                try:
                    compute_part(band, name, M, I, T)
                    bstat["parts"]["%s_T%d" % (name, T)] = {
                        "ok": True, "seconds": round(time.time() - t, 2)}
                except Exception as exc:          # noqa: BLE001
                    log("  ✗ %s %s T=%dK 失败: %s: %s"
                        % (NAMED_BAND[band], name, T, type(exc).__name__, exc))
                    traceback.print_exc()
                    bstat["parts"]["%s_T%d" % (name, T)] = {
                        "ok": False, "seconds": round(time.time() - t, 2),
                        "error": "%s: %s" % (type(exc).__name__, exc)}
                    failed_species.add(name)
            unload_table(table_name(band, name))
            # 每完成一个物种立即增量落盘，下游可先用
            if band_species_done(band, name):
                assemble_band(band, time_up=time_up)
            if time_up:
                break
        bstat["elapsed_s"] = round(time.time() - t_band, 1)
        complete = assemble_band(band, time_up=time_up)
        bstat["complete"] = bool(complete)
        status["bands"][band]["missing_species"] = [
            s for s in PRIORITY[band] if not band_species_done(band, s)]
        all_complete = all_complete and complete
        if time_up:
            for other in bands:
                if other not in status["bands"]:
                    status["bands"][other] = {"complete": False,
                                              "skipped": "time_budget_exceeded"}
            break

    status["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    status["elapsed_s"] = round(time.time() - _wall0, 1)
    status["failed_species"] = sorted(failed_species)
    status["time_budget_exceeded"] = bool(time_up)
    status["all_complete"] = bool(all_complete)
    try:
        with open(status_path, "w", encoding="utf-8") as fh:
            json.dump(status, fh, ensure_ascii=False, indent=1)
    except Exception as exc:
        log("状态文件写入失败: %r" % (exc,))

    log("=" * 78)
    log("完成：总耗时 %.1fs，all_complete=%s，failed_species=%s，status=%s"
        % (time.time() - _wall0, all_complete, sorted(failed_species) or "none",
           status_path))
    if all_complete and not time_up:
        return 0
    if time_up:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
Q2 解析结果回读校验 + 网格/条件统计（供 scenario_summary.md 使用）
=================================================================
读回 Q2解析\\atmosphere_index.csv 与 atmosphere_data\\*.csv，做完整性校验并输出：
  Q2解析\\grid_summary.csv      每个(波段,视点高度)的网格覆盖统计
  Q2解析\\condition_combos.csv  地点/地域/大气参数编号/条件组合统计
  Q2解析\\verify_report.json    行数/抽样比对/物理量范围校验结果
用法: python scripts\\summarize_q2.py
"""
import os
import json
import csv
import collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "Q2解析")
DATA = os.path.join(OUT, "atmosphere_data")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    idx = read_csv(os.path.join(OUT, "atmosphere_index.csv"))
    files = sorted(f for f in os.listdir(DATA) if f.endswith(".csv"))
    rows = []
    per_file = {}
    for fn in files:
        r = read_csv(os.path.join(DATA, fn))
        per_file[fn] = len(r)
        rows.extend(r)
    print("索引块数:", len(idx), "数据文件数:", len(files), "数据行数:", len(rows))

    # ---- 校验 1: 行数 ----
    verify = {"n_index_blocks": len(idx), "n_data_files": len(files),
              "n_data_rows": len(rows), "per_file_rows": per_file}
    idx_sum = sum(int(r["n_rows"]) for r in idx)
    verify["index_n_rows_sum"] = idx_sum
    verify["rows_match"] = idx_sum == len(rows)
    verify["checks"] = []

    # ---- 校验 2: 每块行号连续 + 元数据一致 ----
    by_block = collections.defaultdict(list)
    for r in rows:
        by_block[r["block_id"]].append(r)
    for b, lst in by_block.items():
        row_nos = sorted(int(x["row_no_in_block"]) for x in lst)
        ok_seq = row_nos == list(range(1, len(row_nos) + 1))
        idx_rec = next(x for x in idx if x["block_id"] == b)
        ok_cnt = len(lst) == int(idx_rec["n_rows"])
        meta_keys = ["band", "file", "location", "region_type", "atm_no", "rt_file"]
        ok_meta = all(len(set(x[k] for x in lst)) == 1 and
                      lst[0][k] == idx_rec[k] for k in meta_keys)
        verify["checks"].append({"block_id": b, "row_no_continuous": ok_seq,
                                 "n_rows_matches_index": ok_cnt,
                                 "meta_consistent": ok_meta,
                                 "n_rows": len(lst)})

    # ---- 校验 3: 数值范围 / 空值 ----
    nums = ["viewpoint_altitude_m", "view_azimuth_deg", "view_pitch_deg",
            "target_height_m", "solar_irradiance_W_m2", "path_transmittance",
            "path_radiance_W_m2sr", "background_radiance_W_m2sr"]
    bad = 0
    for r in rows:
        for k in nums:
            try:
                float(r[k])
            except (TypeError, ValueError):
                bad += 1
    verify["n_non_numeric_values"] = bad
    tr_bad = sum(1 for r in rows if not (0.0 <= float(r["path_transmittance"]) <= 1.0))
    verify["n_transmittance_out_of_0_1"] = tr_bad

    # ---- 网格统计（按块 + 视点高度）----
    grid = []
    for b, lst in sorted(by_block.items(), key=lambda kv: int(kv[0])):
        band = lst[0]["band"]
        by_va = collections.defaultdict(list)
        for r in lst:
            by_va[float(r["viewpoint_altitude_m"])].append(r)
        for va in sorted(by_va):
            g = by_va[va]
            els = sorted(set(float(x["view_pitch_deg"]) for x in g))
            azs = sorted(set(float(x["view_azimuth_deg"]) for x in g))
            tgs = sorted(set(float(x["target_height_m"]) for x in g))
            grid.append({
                "block_id": b, "band": band,
                "viewpoint_altitude_m": va, "n_rows": len(g),
                "n_az": len(azs), "n_el": len(els),
                "el_min": els[0], "el_max": els[-1],
                "target_heights": ";".join("%g" % t for t in tgs),
                "expected_if_full_180_per_va_az": len(azs) * 180,
                "coverage_ratio_vs_180": round(len(g) / (len(azs) * 180.0), 4),
            })
    gs_path = os.path.join(OUT, "grid_summary.csv")
    with open(gs_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(grid[0].keys()))
        w.writeheader()
        w.writerows(grid)

    # ---- 条件组合统计 ----
    combos = collections.OrderedDict()
    for b, lst in sorted(by_block.items(), key=lambda kv: int(kv[0])):
        r0 = lst[0]
        key = (r0["band"], r0["location"], r0["region_type"], r0["atm_no"],
               r0["time"], r0["wl_min_um"], r0["wl_max_um"],
               r0["temperature_C"], r0["humidity_pct"], r0["visibility_m"],
               r0["pressure_hpa"], r0["aerosol_model"], r0["atmosphere_model"],
               r0["weather"], r0["pitch_step_deg"], r0["rt_file"])
        combos.setdefault(key, {"n_blocks": 0, "n_rows": 0})
        combos[key]["n_blocks"] += 1
        combos[key]["n_rows"] += len(lst)
    cb_path = os.path.join(OUT, "condition_combos.csv")
    with open(cb_path, "w", encoding="utf-8-sig", newline="") as f:
        cols = ["band", "location", "region_type", "atm_no", "time",
                "wl_min_um", "wl_max_um", "temperature_C", "humidity_pct",
                "visibility_m", "pressure_hpa", "aerosol_model",
                "atmosphere_model", "weather", "pitch_step_deg", "rt_file",
                "n_blocks", "n_rows"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for k, v in combos.items():
            d = dict(zip(cols[:16], k))
            d.update(v)
            w.writerow(d)

    # ---- 各波段物理量范围 ----
    phys = {}
    for b, lst in by_block.items():
        band = lst[0]["band"]
        d = {}
        for k in ["solar_irradiance_W_m2", "path_transmittance",
                  "path_radiance_W_m2sr", "background_radiance_W_m2sr"]:
            vals = [float(x[k]) for x in lst]
            d[k] = {"min": min(vals), "max": max(vals),
                    "mean": sum(vals) / len(vals), "n_unique": len(set(vals))}
        phys[band] = d
    verify["physics_ranges"] = phys
    verify["grid_summary_csv"] = gs_path
    verify["condition_combos_csv"] = cb_path

    with open(os.path.join(OUT, "verify_report.json"), "w", encoding="utf-8") as f:
        json.dump(verify, f, ensure_ascii=False, indent=2)

    print("校验: 行数一致 =", verify["rows_match"],
          "| 非数值 =", verify["n_non_numeric_values"],
          "| 透过率越界 =", verify["n_transmittance_out_of_0_1"])
    for c in verify["checks"]:
        print("  block", c["block_id"], "row_no连续", c["row_no_continuous"],
              "行数匹配", c["n_rows_matches_index"], "元数据一致", c["meta_consistent"],
              "rows", c["n_rows"])
    print("grid_summary ->", gs_path)
    print("condition_combos ->", cb_path)
    print("verify_report ->", os.path.join(OUT, "verify_report.json"))
    return 0 if verify["rows_match"] and bad == 0 and tr_bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

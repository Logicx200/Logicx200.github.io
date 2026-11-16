# -*- coding: utf-8 -*-
"""
Q2_M.csv / Q2_L.csv 大气辐射传输查找表解析器（只读源文件）
==========================================================
源: D:\\XGGDCOSSim2\\Data\\AtomData\\Q2_M.csv (中波红外), Q2_L.csv (长波红外)
编码: GB18030/GBK
结构: 每个“数据块”= 7 行块头(3 组表头 + 取值) + N 行数据(每行 8 列)
      实际交付的这两个文件各只有 1 个数据块。

输出(默认写入 F:\\DeepSeek工作区\\软件参数提取\\Q2解析\\):
  atmosphere_index.csv          每个数据块 1 行
  atmosphere_data\\*.csv         全部数据行（按块+行号分块，默认 10000 行/文件）
  parse_report.json             解析统计 / 校验 / 异常
用法: python scripts\\parse_q2.py [--chunk 10000]
"""
import os
import re
import json
import csv
import sys
import hashlib

SRC_DIR = r"D:\XGGDCOSSim2\Data\AtomData"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "Q2解析")
DATA_DIR = os.path.join(OUT_DIR, "atmosphere_data")

FILES = ["Q2_M.csv", "Q2_L.csv"]

# 8 列数据名
DATA_COLS = [
    "viewpoint_altitude_m",      # 视点海拔高度(米)
    "view_azimuth_deg",          # 视线方位角(度)
    "view_pitch_deg",            # 视线俯仰角(度)
    "target_height_m",           # 目标高度(米)
    "solar_irradiance_W_m2",     # 太阳辐射照度(瓦/平方米)
    "path_transmittance",        # 路径透过率
    "path_radiance_W_m2sr",      # 路径辐射亮度(瓦/(球面度*平方米))
    "background_radiance_W_m2sr",  # 背景辐射亮度(瓦/(球面度*平方米))
]

INDEX_FIELDS = [
    "band", "file", "block_id", "location", "region_type", "atm_no", "rt_file",
    "time", "lon", "lat", "altitude", "wl_min_um", "wl_max_um",
    "temperature_C", "humidity_pct", "visibility_m", "pressure_hpa",
    "aerosol_model", "atmosphere_model", "weather", "pitch_step_deg",
    "n_rows", "row_start", "row_end",
]

META_FIELDS = [
    "band", "file", "block_id", "location", "region_type", "atm_no", "rt_file",
    "time", "lon", "lat", "altitude", "wl_min_um", "wl_max_um",
    "temperature_C", "humidity_pct", "visibility_m", "pressure_hpa",
    "aerosol_model", "atmosphere_model", "weather", "pitch_step_deg",
    "row_no_in_block",
]


def fnum(s, default=None):
    s = (s or "").strip()
    if s == "":
        return default
    try:
        v = float(s)
        if v != v:  # NaN
            return default
        return v
    except ValueError:
        return default


def read_lines(path):
    raw = open(path, "rb").read()
    txt = raw.decode("gb18030", errors="strict")
    return txt.replace("\r\n", "\n").replace("\r", "\n").split("\n"), hashlib.md5(raw).hexdigest(), len(raw)


def split_fields(line):
    return [x.strip() for x in line.split(",")]


def parse_file(fname):
    path = os.path.join(SRC_DIR, fname)
    lines, md5, nbytes = read_lines(path)
    n_total = len(lines)

    blocks = []
    i = 0
    while i < n_total:
        if not lines[i].strip():
            i += 1
            continue
        f0 = split_fields(lines[i])[0]
        if not f0.startswith("波段"):
            # 块外杂行（理论上不存在），记录后跳过
            i += 1
            continue
        # --- 1) 波段/地点/地域/大气参数编号/RT卡片 ---
        blk = {"file": fname}
        hdr = split_fields(lines[i])
        vals = split_fields(lines[i + 1])
        blk["band"] = vals[0]
        blk["location"] = vals[1] if len(vals) > 1 else ""
        blk["region_type"] = vals[2] if len(vals) > 2 else ""
        blk["atm_no"] = vals[3] if len(vals) > 3 else ""
        blk["rt_file"] = vals[4] if len(vals) > 4 else ""
        blk["_hdr1"] = [x for x in hdr if x]
        i += 2

        # --- 2) 绝对时间/经纬度/高度/起止波长 ---
        blk["_hdr2"] = [x for x in split_fields(lines[i]) if x]
        vals = split_fields(lines[i + 1])
        blk["time"] = vals[0]
        blk["lon"] = fnum(vals[1] if len(vals) > 1 else "")
        blk["lat"] = fnum(vals[2] if len(vals) > 2 else "")
        blk["altitude"] = fnum(vals[3] if len(vals) > 3 else "")
        blk["wl_min_um"] = fnum(vals[4] if len(vals) > 4 else "")
        blk["wl_max_um"] = fnum(vals[5] if len(vals) > 5 else "")
        i += 2

        # --- 3) 温度/湿度/能见度/压强/气溶胶/大气模式/天气 + 俯仰角步长 ---
        hdr3 = split_fields(lines[i])
        blk["_hdr3"] = [x for x in hdr3 if x]
        vals = split_fields(lines[i + 1])
        blk["temperature_C"] = fnum(vals[0] if len(vals) > 0 else "")
        blk["humidity_pct"] = fnum(vals[1] if len(vals) > 1 else "")
        blk["visibility_m"] = fnum(vals[2] if len(vals) > 2 else "")
        blk["pressure_hpa"] = fnum(vals[3] if len(vals) > 3 else "")
        blk["aerosol_model"] = vals[4] if len(vals) > 4 else ""
        blk["atmosphere_model"] = vals[5] if len(vals) > 5 else ""
        blk["weather"] = vals[6] if len(vals) > 6 else ""
        # 俯仰角步长在行尾：按表头名定位（原始表头里位于第 2 组末尾，通常 index 16）
        step_idx = 16
        for k, h in enumerate(hdr3):
            if "俯仰角步长" in h:
                step_idx = k
                break
        blk["step_idx"] = step_idx
        blk["pitch_step_deg"] = fnum(vals[step_idx] if len(vals) > step_idx else "")
        i += 2

        # --- 4) 数据列头 ---
        blk["_hdr4"] = [x for x in split_fields(lines[i]) if x]
        i += 1

        # --- 5) 数据行，直到下一个块头或文件尾 ---
        rows = []
        row_start = i + 1  # 1-based 行号(文件内)
        bad_rows = []
        while i < n_total:
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if split_fields(lines[i])[0].startswith("波段"):
                break
            f = split_fields(lines[i])
            if len(f) < 8:
                bad_rows.append({"line_no": i + 1, "raw": s[:200],
                                 "reason": "fields<8", "n_fields": len(f)})
                i += 1
                continue
            rec = [fnum(f[k]) for k in range(8)]
            if any(v is None for v in rec):
                bad_rows.append({"line_no": i + 1, "raw": s[:200],
                                 "reason": "non-numeric", "fields": f[:8]})
                i += 1
                continue
            rows.append(rec)
            i += 1
        row_end = row_start + len(rows) - 1 if rows else row_start - 1

        blk["row_start"] = row_start
        blk["row_end"] = row_end
        blk["n_rows"] = len(rows)
        blk["bad_rows"] = bad_rows
        blk["rows"] = rows
        blocks.append(blk)

    return {"file": fname, "md5": md5, "bytes": nbytes, "lines": n_total,
            "blocks": blocks}


def grid_stats(rows):
    """数据行网格统计"""
    if not rows:
        return {}
    col = list(zip(*rows))
    names = DATA_COLS
    out = {}
    for k, name in enumerate(names[:4]):  # 前 4 列是网格坐标
        uniq = sorted(set(col[k]))
        out[name] = {"n_unique": len(uniq),
                     "min": uniq[0], "max": uniq[-1],
                     "values": uniq if len(uniq) <= 64 else None}
    for k, name in enumerate(names[4:], start=4):  # 物理量
        vals = col[k]
        out[name] = {"n_unique": len(set(vals)),
                     "min": min(vals), "max": max(vals),
                     "mean": sum(vals) / len(vals)}
    return out


def main():
    chunk = 10000
    if "--chunk" in sys.argv:
        chunk = int(sys.argv[sys.argv.index("--chunk") + 1])
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    report = {"source_dir": SRC_DIR, "files": [], "issues": []}
    index_rows = []
    total_rows_written = 0
    block_seq = 0

    for fname in FILES:
        path = os.path.join(SRC_DIR, fname)
        if not os.path.exists(path):
            report["issues"].append(f"缺少源文件: {path}")
            continue
        res = parse_file(fname)
        finfo = {"file": fname, "md5": res["md5"], "bytes": res["bytes"],
                 "lines_in_file": res["lines"], "n_blocks": len(res["blocks"]),
                 "blocks": []}
        for blk in res["blocks"]:
            block_seq += 1
            bid = block_seq
            blk["block_id"] = bid
            rows = blk["rows"]
            total_rows_written += len(rows)
            idx = {
                "band": blk["band"], "file": fname, "block_id": bid,
                "location": blk["location"], "region_type": blk["region_type"],
                "atm_no": blk["atm_no"], "rt_file": blk["rt_file"],
                "time": blk["time"], "lon": blk["lon"], "lat": blk["lat"],
                "altitude": blk["altitude"],
                "wl_min_um": blk["wl_min_um"], "wl_max_um": blk["wl_max_um"],
                "temperature_C": blk["temperature_C"],
                "humidity_pct": blk["humidity_pct"],
                "visibility_m": blk["visibility_m"],
                "pressure_hpa": blk["pressure_hpa"],
                "aerosol_model": blk["aerosol_model"],
                "atmosphere_model": blk["atmosphere_model"],
                "weather": blk["weather"],
                "pitch_step_deg": blk["pitch_step_deg"],
                "n_rows": blk["n_rows"],
                "row_start": blk["row_start"], "row_end": blk["row_end"],
            }
            index_rows.append(idx)

            # 分块写数据 CSV
            tag = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", fname.rsplit(".", 1)[0])
            parts = []
            for off in range(0, len(rows), chunk):
                part_no = off // chunk + 1
                fn = f"atmo_{tag}_b{bid:02d}_part{part_no:02d}.csv"
                fp = os.path.join(DATA_DIR, fn)
                with open(fp, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(META_FIELDS + DATA_COLS)
                    for local_i, rec in enumerate(rows[off:off + chunk], start=off):
                        row_no = local_i + 1
                        w.writerow([
                            blk["band"], fname, bid, blk["location"],
                            blk["region_type"], blk["atm_no"], blk["rt_file"],
                            blk["time"], blk["lon"], blk["lat"], blk["altitude"],
                            blk["wl_min_um"], blk["wl_max_um"],
                            blk["temperature_C"], blk["humidity_pct"],
                            blk["visibility_m"], blk["pressure_hpa"],
                            blk["aerosol_model"], blk["atmosphere_model"],
                            blk["weather"], blk["pitch_step_deg"], row_no,
                        ] + [f"{x:.10g}" for x in rec])
                parts.append({"file": fn, "rows": len(rows[off:off + chunk]),
                              "row_from": off + 1, "row_to": min(off + chunk, len(rows))})

            bstat = {
                "block_id": bid, "band": blk["band"], "n_rows": blk["n_rows"],
                "row_start": blk["row_start"], "row_end": blk["row_end"],
                "n_bad_rows": len(blk["bad_rows"]),
                "bad_rows_sample": blk["bad_rows"][:20],
                "data_files": parts,
                "grid": grid_stats(rows),
                "raw_headers": {
                    "header1": blk["_hdr1"], "header2": blk["_hdr2"],
                    "header3": blk["_hdr3"], "header4": blk["_hdr4"],
                },
            }
            # 网格完备性检查：视点高度 x 方位角 组合的行数
            pairs = {}
            for rec in rows:
                key = (rec[0], rec[1])
                pairs[key] = pairs.get(key, 0) + 1
            bstat["n_view_alt"] = len(set(k[0] for k in pairs))
            bstat["n_az"] = len(set(k[1] for k in pairs))
            bstat["n_va_az_pairs"] = len(pairs)
            counts = sorted(set(pairs.values()))
            bstat["rows_per_va_az_counts"] = counts
            finfo["blocks"].append(bstat)
        report["files"].append(finfo)

    # 写索引 CSV
    idx_path = os.path.join(OUT_DIR, "atmosphere_index.csv")
    with open(idx_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        for r in index_rows:
            w.writerow(r)

    # 校验：索引 n_rows 之和 vs 实际写出
    idx_sum = sum(r["n_rows"] for r in index_rows)
    report["summary"] = {
        "n_blocks": len(index_rows),
        "index_rows": len(index_rows),
        "rows_in_index_sum": idx_sum,
        "rows_written_to_csv": total_rows_written,
        "rows_match": idx_sum == total_rows_written,
        "output_index": idx_path,
        "output_data_dir": DATA_DIR,
    }
    if idx_sum != total_rows_written:
        report["issues"].append(
            f"行数不一致: index_sum={idx_sum} written={total_rows_written}")

    # 负值/物理量合理性检查（透过率应在 0~1）
    for finfo in report["files"]:
        for b in finfo["blocks"]:
            tr = b["grid"].get("path_transmittance", {})
            if tr and (tr.get("min", 0) < 0 or tr.get("max", 1) > 1.0000001):
                report["issues"].append(
                    f"{finfo['file']} block{b['block_id']}: 透过率超界 "
                    f"[{tr['min']}, {tr['max']}]")

    rp = os.path.join(OUT_DIR, "parse_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("== 解析完成 ==")
    for r in index_rows:
        print(f"  block{r['block_id']:02d} {r['band']} "
              f"{r['location']}/{r['region_type']}/{r['atm_no']} "
              f"rows={r['n_rows']} [{r['row_start']}-{r['row_end']}] "
              f"T={r['temperature_C']} RH={r['humidity_pct']} "
              f"VIS={r['visibility_m']} P={r['pressure_hpa']} "
              f"{r['aerosol_model']}/{r['atmosphere_model']}/{r['weather']} "
              f"step={r['pitch_step_deg']} wl=[{r['wl_min_um']},{r['wl_max_um']}]")
    print(f"  索引 -> {idx_path}")
    print(f"  数据 -> {DATA_DIR}  (共 {total_rows_written} 行)")
    print(f"  报告 -> {rp}")
    if report["issues"]:
        print("  !! 问题:")
        for it in report["issues"]:
            print("    -", it)
    return 0 if not report["issues"] else 1


if __name__ == "__main__":
    sys.exit(main())

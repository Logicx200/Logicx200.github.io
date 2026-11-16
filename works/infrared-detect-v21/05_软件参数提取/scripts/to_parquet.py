# -*- coding: utf-8 -*-
"""
把 Q2 解析结果合并为单个 parquet（便于另一个模型直接读取）
==========================================================
输入: Q2解析\\atmosphere_data\\*.csv（CSV 分块）
输出: Q2解析\\atmosphere_data.parquet
      Q2解析\\parquet_report.json （行数/列/dtype/校验）
用法: python scripts\\to_parquet.py
"""
import os
import json
import glob
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "Q2解析")
DATA = os.path.join(OUT, "atmosphere_data")

CAT_COLS = ["band", "file", "location", "region_type", "atm_no", "rt_file",
            "time", "aerosol_model", "atmosphere_model", "weather"]
FLOAT_COLS = ["lon", "lat", "altitude", "wl_min_um", "wl_max_um",
              "temperature_C", "humidity_pct", "visibility_m", "pressure_hpa",
              "pitch_step_deg", "viewpoint_altitude_m", "view_azimuth_deg",
              "view_pitch_deg", "target_height_m", "solar_irradiance_W_m2",
              "path_transmittance", "path_radiance_W_m2sr",
              "background_radiance_W_m2sr"]
INT_COLS = ["block_id", "row_no_in_block"]


def main():
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    frames = [pd.read_csv(p, encoding="utf-8-sig") for p in files]
    df = pd.concat(frames, ignore_index=True)
    for c in CAT_COLS:
        df[c] = df[c].astype("category")
    for c in FLOAT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in INT_COLS:
        df[c] = df[c].astype("int32")

    pq = os.path.join(OUT, "atmosphere_data.parquet")
    df.to_parquet(pq, index=False, compression="zstd")

    # 回读校验
    back = pd.read_parquet(pq)
    chk = {
        "n_rows_csv": int(len(df)),
        "n_rows_parquet": int(len(back)),
        "rows_match": int(len(df)) == int(len(back)),
        "n_cols": int(len(back.columns)),
        "columns": list(back.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "per_block_rows": {str(k): int(v) for k, v in
                           df.groupby("block_id", observed=True).size().items()},
        "path_transmittance_min_max": [float(df["path_transmittance"].min()),
                                       float(df["path_transmittance"].max())],
        "nan_counts": {c: int(df[c].isna().sum()) for c in FLOAT_COLS},
        "parquet": pq,
        "parquet_bytes": os.path.getsize(pq),
        "source_csv_files": [os.path.basename(p) for p in files],
    }
    with open(os.path.join(OUT, "parquet_report.json"), "w", encoding="utf-8") as f:
        json.dump(chk, f, ensure_ascii=False, indent=2)

    print(f"parquet -> {pq}  ({chk['parquet_bytes']/1024:.1f} KB)")
    print(f"rows csv={chk['n_rows_csv']} parquet={chk['n_rows_parquet']} match={chk['rows_match']}")
    print("per block:", chk["per_block_rows"])
    assert chk["rows_match"] and all(v == 0 for v in chk["nan_counts"].values())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

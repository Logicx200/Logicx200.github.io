# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

OUT = Path(r"F:\DeepSeek工作区\正式仿真")
OUT.mkdir(parents=True, exist_ok=True)


def parse(path, band):
    lines = Path(path).read_text(encoding="gb18030", errors="replace").splitlines()
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line.startswith("中波红外") or line.startswith("长波红外"):
            header = [x.strip() for x in line.split(",")]
            blk = {"band": header[0], "location": header[1], "region": header[2],
                   "atm_no": header[3], "rt_file": header[4] if len(header) > 4 else ""}
            # time line
            j = i + 1
            if j < n and lines[j].startswith("绝对时间"):
                j += 1
            if j < n:
                t = [x.strip() for x in lines[j].split(",")]
                blk["time"] = t[0] if len(t) > 0 else ""
                blk["lon"] = t[1] if len(t) > 1 else ""
                blk["lat"] = t[2] if len(t) > 2 else ""
                blk["alt"] = t[3] if len(t) > 3 else ""
                blk["wl_min"] = t[4] if len(t) > 4 else ""
                blk["wl_max"] = t[5] if len(t) > 5 else ""
            j = i + 2
            # conditions line
            if j < n and lines[j].startswith("温度"):
                j += 1
            if j < n:
                c = [x.strip() for x in lines[j].split(",")]
                blk["temperature"] = c[0] if len(c) > 0 else ""
                blk["humidity"] = c[1] if len(c) > 1 else ""
                blk["visibility"] = c[2] if len(c) > 2 else ""
                blk["pressure"] = c[3] if len(c) > 3 else ""
                blk["aerosol"] = c[4] if len(c) > 4 else ""
                blk["atmosphere"] = c[5] if len(c) > 5 else ""
                blk["weather"] = c[6] if len(c) > 6 else ""
                blk["pitch_step"] = c[-1] if c else ""
            # data header
            j = i + 4
            if j < n and lines[j].startswith("视点海拔"):
                j += 1
            rows = 0
            while j < n and lines[j].strip() and not (lines[j].startswith("中波红外") or lines[j].startswith("长波红外")):
                rows += 1
                j += 1
            blk["n_rows"] = rows
            blk["start_line"] = i + 1
            blocks.append(blk)
            i = j
        else:
            i += 1
    return blocks


m = parse(r"D:\XGGDCOSSim2\Data\AtomData\Q2_M.csv", "MWIR")
l = parse(r"D:\XGGDCOSSim2\Data\AtomData\Q2_L.csv", "LWIR")
print("MWIR blocks", len(m), "rows", sum(b["n_rows"] for b in m))
print("LWIR blocks", len(l), "rows", sum(b["n_rows"] for b in l))

idx = m + l
(OUT / "q2_index_lead.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")

def uniq(key):
    vals = {}
    for b in idx:
        vals[b[key]] = vals.get(b[key], 0) + 1
    return vals

print("locations:", uniq("location"))
print("regions:", uniq("region"))
print("atm_no:", uniq("atm_no"))
print("aerosol:", uniq("aerosol"))
print("atmosphere:", uniq("atmosphere"))
print("wl ranges M:", sorted({(b["wl_min"], b["wl_max"]) for b in m}))
print("wl ranges L:", sorted({(b["wl_min"], b["wl_max"]) for b in l}))
print("temps:", sorted({b["temperature"] for b in idx}))
print("humidity:", sorted({b["humidity"] for b in idx}))
print("vis:", sorted({b["visibility"] for b in idx}))
print("pitch steps:", sorted({b["pitch_step"] for b in idx}))

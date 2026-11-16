# -*- coding: utf-8 -*-
"""Fetch MERRA-2/CERES daily AOD550 + PWV from NASA POWER for candidate sites."""
import csv
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_power")
os.makedirs(OUT, exist_ok=True)

SITES = [
    ("Dunhuang", 94.794, 40.038, "沙漠背景/浮尘（塔克拉玛干东缘）"),
    ("Minqin", 102.959, 38.607, "沙漠边缘/浮尘（巴丹吉林-腾格里）"),
    ("Dalanzadgad", 104.419, 43.577, "戈壁沙尘（蒙古高原）"),
    ("Kashi", 75.930, 39.504, "沙漠沙尘（塔里木西缘）"),
    ("SACOL", 104.137, 35.946, "半干旱乡村（黄土高原）"),
    ("XiangHe", 116.962, 39.754, "乡村农业/燃烧（华北平原）"),
    ("Taihu", 120.215, 31.421, "乡村/城市混合（长江三角洲）"),
    ("Beijing", 116.381, 39.977, "城市/工业（京津冀）"),
    ("SONET_Shanghai", 121.481, 31.284, "城市/近岸（长三角）"),
    ("Hong_Kong_PolyU", 114.180, 22.303, "城市/近岸（珠三角）"),
    ("Dongsha_Island", 116.729, 20.699, "海岛/海洋清洁（南海北部）"),
    ("Lanai", -156.922, 20.735, "远洋清洁（太平洋）"),
    ("Nauru", 166.916, -0.521, "热带海洋清洁"),
    ("Lhasa", 91.033, 29.646, "高原清洁/低水汽"),
    ("Alta_Floresta", -56.104, -9.871, "热带农业燃烧（亚马逊）"),
    ("Solar_Village", 46.397, 24.907, "强沙尘（阿拉伯半岛）"),
]

BASE = ("https://power.larc.nasa.gov/api/temporal/daily/point?"
        "parameters=AOD_55,PW&community=AG&longitude={lon}&latitude={lat}"
        "&start=20150101&end=20241231&format=CSV")

summary = []
for name, lon, lat, desc in SITES:
    path = os.path.join(OUT, name + ".csv")
    if not os.path.exists(path) or os.path.getsize(path) < 2000:
        url = BASE.format(lon=lon, lat=lat)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=90) as r:
                    raw = r.read().decode("utf-8", "replace")
                if "-END HEADER-" in raw and len(raw) > 2000:
                    open(path, "w", encoding="utf-8").write(raw)
                    print("OK", name, len(raw), flush=True)
                    break
                else:
                    print("SHORT", name, len(raw), flush=True)
            except Exception as e:
                print("ERR", name, attempt, e, flush=True)
                time.sleep(5)
    else:
        print("CACHED", name, flush=True)

    if not os.path.exists(path):
        continue
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("YEAR,DOY"):
            header_idx = i
            break
    if header_idx is None:
        print("NOHEADER", name)
        continue
    for ln in lines[header_idx + 1:]:
        parts = ln.split(",")
        if len(parts) != 4:
            continue
        try:
            pw = float(parts[3]); aod = float(parts[2])
        except ValueError:
            continue
        if pw > -900 and aod > -900:
            rows.append((pw, aod))
    if not rows:
        print("NOROWS", name)
        continue
    import statistics as st
    pws = [r[0] for r in rows]; aods = [r[1] for r in rows]
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))]
    summary.append({
        "site": name, "lon": lon, "lat": lat, "desc": desc, "n": len(rows),
        "pw_med": round(st.median(pws), 2),
        "pw_p10": round(q(pws, 0.1), 2),
        "pw_p90": round(q(pws, 0.9), 2),
        "aod_med": round(st.median(aods), 3),
        "aod_p10": round(q(aods, 0.1), 3),
        "aod_p90": round(q(aods, 0.9), 3),
    })

with open(os.path.join(HERE, "_power_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    w.writeheader(); w.writerows(summary)
print(json.dumps(summary, ensure_ascii=False, indent=1))

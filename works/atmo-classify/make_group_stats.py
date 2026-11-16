# -*- coding: utf-8 -*-
"""多站汇总：按工况把多个站点的逐日 PWV/AOD550 做统计，演示“通用参数”的做法。"""
import csv
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
POWER = os.path.join(HERE, "_power")

GROUPS = {
    "沙漠背景/浮尘": ["Dunhuang", "Minqin", "Dalanzadgad"],
    "沙漠沙尘事件": ["Kashi", "Solar_Village"],
    "乡村清洁": ["SACOL"],
    "乡村农业/燃烧": ["XiangHe", "Taihu", "Alta_Floresta"],
    "城市/工业": ["Beijing", "SONET_Shanghai"],
    "海岛/近岸污染": ["Hong_Kong_PolyU"],
    "海岛/海洋清洁": ["Dongsha_Island", "Lanai", "Nauru"],
    "高原清洁/低水汽": ["Lhasa"],
}


def load(site):
    path = os.path.join(POWER, site + ".csv")
    lines = open(path, "r", encoding="utf-8", errors="replace").read().splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("YEAR,DOY"))
    pw, aod = [], []
    for ln in lines[i + 1:]:
        p = ln.split(",")
        if len(p) != 4:
            continue
        try:
            a, b = float(p[2]), float(p[3])
        except ValueError:
            continue
        if a > -900 and b > -900:
            aod.append(a); pw.append(b)
    return pw, aod


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))]


site_stats = {}
pooled = {}
for site in {s for g in GROUPS.values() for s in g}:
    pw, aod = load(site)
    site_stats[site] = dict(
        n=len(pw), pw_med=st.median(pw), aod_med=st.median(aod),
        pw_p10=q(pw, .1), pw_p90=q(pw, .9), aod_p10=q(aod, .1), aod_p90=q(aod, .9),
    )

rows = []
for group, sites in GROUPS.items():
    all_pw = []; all_aod = []
    for s in sites:
        pw, aod = load(s)
        all_pw += pw; all_aod += aod
    site_pw_med = [site_stats[s]["pw_med"] for s in sites]
    site_aod_med = [site_stats[s]["aod_med"] for s in sites]
    rows.append(dict(
        group=group, sites=",".join(sites),
        n_sites=len(sites), n_days=len(all_pw),
        pw_med=round(st.median(all_pw), 2),
        pw_p10=round(q(all_pw, .1), 2), pw_p90=round(q(all_pw, .9), 2),
        aod_med=round(st.median(all_aod), 3),
        aod_p10=round(q(all_aod, .1), 3), aod_p90=round(q(all_aod, .9), 3),
        site_pw_med_min=round(min(site_pw_med), 2), site_pw_med_max=round(max(site_pw_med), 2),
        site_aod_med_min=round(min(site_aod_med), 3), site_aod_med_max=round(max(site_aod_med), 3),
    ))

with open(os.path.join(HERE, "工况统计_多站汇总.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

with open(os.path.join(HERE, "_site_stats.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["site", "n", "pw_med", "pw_p10", "pw_p90", "aod_med", "aod_p10", "aod_p90"])
    w.writeheader()
    for s, v in site_stats.items():
        w.writerow({"site": s, **{k: round(v[k], 3) if isinstance(v[k], float) else v[k] for k in ["n", "pw_med", "pw_p10", "pw_p90", "aod_med", "aod_p10", "aod_p90"]}})

print(json.dumps(rows, ensure_ascii=False, indent=1))

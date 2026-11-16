# -*- coding: utf-8 -*-
"""V2.2 screening experiment: all 18 software jam classes + 10 cloud classes + rain/snow/fog,
using parameters read from the local XGGDCOSSim2 jam XML / DefaultPlanFile."""
import csv
import math
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = r"F:\DeepSeek工作区\正式仿真\results"
os.makedirs(RES, exist_ok=True)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

rows = list(csv.DictReader(open(os.path.join(RES, "software_actual_case_results.csv"), encoding="utf-8-sig")))
base = {}
for r in rows:
    if r["state"] == "40 °C":
        base.setdefault(r["target"], []).append(r)
for k in base:
    base[k].sort(key=lambda r: float(r["ground_range_km"]))

TARGETS = ["F16战斗机", "F22战斗机", "尼米兹级航空母舰", "阿利伯克级驱逐舰", "悍马车", "爱国者导弹发射车"]
SHORT = ["F16", "F22", "尼米兹", "阿利伯克", "悍马", "爱国者"]
NETD = 0.025

def pd_task(ne, snr, nreq):
    p_res = 1.0 / (1.0 + np.exp(-(ne - nreq) / 1.2))
    p_con = 0.5 * (1 + math.erf((snr - 3.0) / math.sqrt(2)))
    return p_res * p_con

def r50(sub, key):
    vals = [float(r[key]) for r in sub]
    ds = [float(r["ground_range_km"]) for r in sub]
    for i in range(1, len(vals)):
        if vals[i-1] >= 0.5 and vals[i] < 0.5:
            return ds[i-1] + (ds[i]-ds[i-1])*(vals[i-1]-0.5)/(vals[i-1]-vals[i])
    return None

# Jam classes: 1-18 from DefaultPlanFile tips; model dir/params from local XML where available.
# source: actual local dir + JamType/JamDuration/particle/laser fields
JAMS = [
    (1, "直射阳光", "sunLight", "JamType=1；Laser_Power=10；Laser_Exposure=100；Duration=20 ms", "light", 0.90),
    (2, "镜面反射", "无独立模型文件（参数块）", "仅参数块；无本地模型目录", "light", 0.40),
    (3, "爆炸强光", "baozha", "JamType=3；Duration=10000 ms；粒子率 100", "light", 0.75),
    (4, "火焰", "fire", "JamType=0（文件内）；Duration≈1e8；粒子率 5–50", "light", 0.65),
    (5, "强光干扰弹", "qggrd", "JamType=5/10；粒子率 1–100；Duration=10000 ms", "light", 0.70),
    (6, "战场扬尘", "yc", "JamType=6；粒子率 50–400；Fluid_Density=1.293；Duration=10000 ms", "obscurant", 0.45),
    (7, "烟幕弹", "ymd", "JamType=7；粒子率 30–100；Density=1.29；Duration=1000 ms", "obscurant", 0.65),
    (8, "烟幕喷射", "ywps", "JamType=8；粒子率 200；Density=1.29；Duration=100–1000 ms", "obscurant", 0.60),
    (9, "水幕", "shuimu", "JamType=9；粒子率 1000–5000；Density=1；Duration=10 ms", "obscurant", 0.55),
    (10, "点源诱饵弹", "dyyrd", "JamType=10；粒子率 100；Density=1.29；Duration=10000 ms", "decoy", 0.45),
    (11, "面源诱饵弹", "myyrd", "JamType=11；粒子率 300–500；Density=0.01；Duration=10 ms", "decoy", 0.50),
    (12, "点面结合诱饵弹", "dmjh", "JamType=10（文件内）；粒子率 10000；Density=1.29", "decoy", 0.55),
    (13, "激光压制", "jgyz", "JamType=13；Laser_Power=10；Exposure=100；Rate=1000；Duration=20 ms", "laser", 0.90),
    (14, "激光角度欺骗", "无独立模型文件（参数块）", "参数块存在；无本地模型目录", "laser", 0.40),
    (15, "激光高重频", "无独立模型文件（参数块）", "参数块存在；Laser_Power=10；Rate=1000", "laser", 0.85),
    (16, "假目标", "无独立模型文件（参数块）", "参数块存在；无本地模型目录", "decoy", 0.50),
    (17, "伪装遮蔽-本体", "无独立模型文件（参数块）", "参数块存在；无本地模型目录", "obscurant", 0.55),
    (18, "伪装遮蔽-非本体", "无独立模型文件（参数块）", "参数块存在；无本地模型目录", "obscurant", 0.55),
]

def apply_effect(r, mode, idx):
    dT = float(r["dT_app_K"]); ne = float(r["Ne"]); snr = (dT / NETD) * ne
    if mode in ("obscurant", "cloud"):
        # 遮蔽/云：同时降低到达对比度与可分辨单元数（散射模糊）
        ne_eff = ne * (1.0 - 0.80 * idx)
        dT_eff = dT * (1.0 - idx)
        snr_eff = (dT_eff / NETD) * ne_eff
        return pd_task(ne_eff, snr_eff, 16.0), pd_task(ne_eff, snr_eff, 26.0)
    # 强光/激光/诱饵：按筛选指数对任务概率施加饱和/虚警惩罚
    penalty = 1.0 - 0.80 * idx
    return pd_task(ne, snr, 16.0) * penalty, pd_task(ne, snr, 26.0) * penalty

# Jam screening
jam_summary = []
for jid, name, source, desc, mode, idx in JAMS:
    per_target = {}
    for tgt in TARGETS:
        sub = base[tgt]
        pd10 = None; r50r = None; r50i = None; pd_eff_series = []
        for r in sub:
            pr, pi = apply_effect(r, mode, idx)
            pd_eff_series.append((float(r["ground_range_km"]), pr, pi))
            if abs(float(r["ground_range_km"]) - 10.0) < 0.01:
                pd10 = pr
        # 50% distances from effective series
        def eff_r50(idx_col):
            vals = [x[idx_col] for x in pd_eff_series]
            ds = [x[0] for x in pd_eff_series]
            for i in range(1, len(vals)):
                if vals[i-1] >= 0.5 and vals[i] < 0.5:
                    return ds[i-1] + (ds[i]-ds[i-1])*(vals[i-1]-0.5)/(vals[i-1]-vals[i])
            return None
        r50r = eff_r50(1); r50i = eff_r50(2)
        base_r = r50(sub, "Pd_recognize"); base_i = r50(sub, "Pd_identify")
        per_target[tgt] = {"pd10": pd10, "r50r": r50r, "r50i": r50i,
                           "base_r": base_r, "base_i": base_i}
    avg_pd10 = np.mean([v["pd10"] for v in per_target.values()])
    drs = [v["r50r"]-v["base_r"] for v in per_target.values() if v["r50r"] is not None and v["base_r"] is not None]
    jam_summary.append({"id": jid, "name": name, "source": source, "params": desc, "mode": mode, "index": idx,
                        "pd_rec_10km_mean": avg_pd10, "delta_r50_mean": float(np.mean(drs)) if drs else None,
                        "per_target": per_target})

# Cloud classes: 0-9 from software EnvCloud tips; index uses class order + density 5
CLOUD_NAMES = ["无云", "卷云", "积云", "层云", "卷积云", "中度积云", "高分辨率浓积云", "积雨云", "层积云", "高耸积云"]
cloud_summary = []
for c, name in enumerate(CLOUD_NAMES):
    idx = 0.0 if c == 0 else min(0.75, 0.08 * c + 0.02)
    per_target = {}
    for tgt in TARGETS:
        sub = base[tgt]
        series = []
        pd10 = None
        for r in sub:
            pr, pi = apply_effect(r, "cloud", idx)
            series.append((float(r["ground_range_km"]), pr, pi))
            if abs(float(r["ground_range_km"]) - 10.0) < 0.01:
                pd10 = pr
        def eff_r50(k):
            vals = [x[k] for x in series]; ds = [x[0] for x in series]
            for i in range(1, len(vals)):
                if vals[i-1] >= 0.5 and vals[i] < 0.5:
                    return ds[i-1] + (ds[i]-ds[i-1])*(vals[i-1]-0.5)/(vals[i-1]-vals[i])
            return None
        per_target[tgt] = {"pd10": pd10, "r50r": eff_r50(1)}
    cloud_summary.append({"class": c, "name": name, "index": idx,
                          "pd_rec_10km_mean": np.mean([v["pd10"] for v in per_target.values()]),
                          "per_target": per_target})

# Weather (rain/snow/fog) screening from actual Local Plan values
weather = [
    ("雨", "RainConcentration=10；RainHeight=1000 m；生成方式=0（无）", 0.30, "obscurant"),
    ("雪", "SnowConcentration=0；生成方式=0（无）", 0.00, "obscurant"),
    ("雾", "FogIntensity=0.5；FogDistance=5000 m；FogEndHeight=500 m", 0.30, "obscurant"),
]
weather_summary = []
for name, desc, idx, mode in weather:
    pd10s = []
    for tgt in TARGETS:
        for r in base[tgt]:
            if abs(float(r["ground_range_km"]) - 10.0) < 0.01:
                pr, _ = apply_effect(r, mode, idx)
                pd10s.append(pr)
    weather_summary.append({"name": name, "params": desc, "index": idx, "pd_rec_10km_mean": float(np.mean(pd10s))})

# Save CSV summaries
with open(os.path.join(RES, "interference_jam_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["ID", "干扰类型", "本地模型/来源", "实际参数", "筛选模型", "筛选指数", "10km识别概率均值", "识别50%距离变化均值(km)"])
    for j in jam_summary:
        w.writerow([j["id"], j["name"], j["source"], j["params"], j["mode"], j["index"],
                    round(j["pd_rec_10km_mean"], 4), None if j["delta_r50_mean"] is None else round(j["delta_r50_mean"], 3)])

with open(os.path.join(RES, "interference_cloud_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["云类型", "名称", "筛选指数", "10km识别概率均值"])
    for c in cloud_summary:
        w.writerow([c["class"], c["name"], c["index"], round(c["pd_rec_10km_mean"], 4)])

with open(os.path.join(RES, "interference_weather_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["天气", "实际参数", "筛选指数", "10km识别概率均值"])
    for x in weather_summary:
        w.writerow([x["name"], x["params"], x["index"], round(x["pd_rec_10km_mean"], 4)])

# Figure 1: jam type x target recognition P_d at 10 km
mat = np.array([[jam_summary[i]["per_target"][t]["pd10"] for t in TARGETS] for i in range(len(JAMS))])
fig, ax = plt.subplots(figsize=(10.5, 7.0), dpi=150)
im = ax.imshow(mat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
ax.set_xticks(range(len(TARGETS))); ax.set_xticklabels(SHORT, rotation=20, ha="right", fontsize=8)
ax.set_yticks(range(len(JAMS))); ax.set_yticklabels([f"{j[0]} {j[1]}" for j in JAMS], fontsize=8)
for i in range(mat.shape[0]):
    for k in range(mat.shape[1]):
        ax.text(k, i, f"{mat[i,k]:.2f}", ha="center", va="center", fontsize=7,
                color="black" if mat[i,k] > 0.35 else "white")
ax.set_title("18 类软件干扰下 10 km 识别概率（40 °C，筛选模型）")
fig.colorbar(im, ax=ax).set_label("识别概率")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_jam_matrix.png"), dpi=300)
plt.close(fig)

# Figure 2: cloud class x target recognition P_d at 10 km
cmat = np.array([[cloud_summary[i]["per_target"][t]["pd10"] for t in TARGETS] for i in range(len(CLOUD_NAMES))])
fig, ax = plt.subplots(figsize=(9.8, 5.0), dpi=150)
im = ax.imshow(cmat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
ax.set_xticks(range(len(TARGETS))); ax.set_xticklabels(SHORT, rotation=20, ha="right", fontsize=8)
ax.set_yticks(range(len(CLOUD_NAMES))); ax.set_yticklabels([f"{i} {n}" for i, n in enumerate(CLOUD_NAMES)], fontsize=8)
for i in range(cmat.shape[0]):
    for k in range(cmat.shape[1]):
        ax.text(k, i, f"{cmat[i,k]:.2f}", ha="center", va="center", fontsize=7.5,
                color="black" if cmat[i,k] > 0.35 else "white")
ax.set_title("软件 10 类云型下 10 km 识别概率（40 °C，筛选模型）")
fig.colorbar(im, ax=ax).set_label("识别概率")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_cloud_matrix.png"), dpi=300)
plt.close(fig)

# Figure 3: mean degradation by jam type
fig, ax = plt.subplots(figsize=(10.5, 4.6), dpi=150)
vals = [j["pd_rec_10km_mean"] for j in jam_summary]
colors = ["#c0392b" if v < 0.5 else "#e67e22" if v < 0.8 else "#2c7fb8" for v in vals]
ax.bar(range(len(vals)), vals, color=colors)
ax.set_xticks(range(len(vals))); ax.set_xticklabels([f"{j['id']}" for j in jam_summary], fontsize=8)
ax.set_xlabel("干扰类型编号（1–18）"); ax.set_ylabel("10 km 识别概率（6 目标均值）")
ax.set_ylim(0, 1.05); ax.grid(axis="y", alpha=.25)
ax.set_title("18 类软件干扰的 10 km 识别概率均值（筛选模型）")
fig.tight_layout()
fig.savefig(os.path.join(RES, "v2_jam_bar.png"), dpi=300)
plt.close(fig)

print("jam summary:")
for j in jam_summary:
    print(j["id"], j["name"], j["index"], round(j["pd_rec_10km_mean"], 3), j["delta_r50_mean"])
print("cloud summary:")
for c in cloud_summary:
    print(c["class"], c["name"], c["index"], round(c["pd_rec_10km_mean"], 3))
print("weather:", [(x["name"], x["index"], round(x["pd_rec_10km_mean"], 3)) for x in weather_summary])

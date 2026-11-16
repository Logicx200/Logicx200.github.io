# -*- coding: utf-8 -*-
"""
软件内实际参数正式算例：
- 背景模型：与那国岛（软件唯一实际背景模型，环境温度 20 °C，0–60 °C）
- 目标模型：软件模型库 6 个目标（F16/F22/nimitz/albk/hm/agzfsc）
- 气象工况：DefaultPlanFile 实际设置：晴天、15 °C、50%RH、1013 hPa、能见度 10 km、干净大陆、美国标准大气、不考虑湍流
- 传感器：软件显示参数锚点（中波 3.7–4.8 μm / 3.75°×3° / 1024×768 / 50 Hz / 8000 m / −90°）+ 本报告辐射参数
"""
import json
import math
import os
import csv

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = r"F:\DeepSeek工作区\正式仿真\results"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
    "axes.unicode_minus": False,
    "mathtext.fontset": "dejavusans",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# ---------- HITRAN cross sections ----------
d = np.load(r"F:\DeepSeek工作区\大气工况分类图\_xsect_3_5um.npz")
NU = d["nu"]  # cm-1
XS = {k: d[k] for k in ("H2O", "CO2", "CH4")}

wl_um = np.linspace(3.7, 4.8, 441)
nu_cm = 1e4 / wl_um

def xs(key):
    return np.interp(nu_cm, NU, XS[key], left=0.0, right=0.0)

# Planck
H = 6.62607015e-34; C = 2.99792458e8; KB = 1.380649e-23
wl_m = wl_um * 1e-6

def planck_lam(T):
    return 2*H*C**2/wl_m**5 / np.expm1(H*C/(wl_m*KB*T))  # W/m2/sr/m

def planck_band(T):
    return np.trapezoid(planck_lam(T), wl_m)  # W/m2/sr

T_GRID = np.linspace(150.0, 500.0, 3501)
B_GRID = np.array([planck_band(T) for T in T_GRID])

def t_app(L):
    return np.interp(L, B_GRID, T_GRID)

# ---------- actual plan weather ----------
T_AIR_C = 15.0
RH = 0.50
P_HPA = 1013.0
VIS_KM = 10.0
ALPHA = 1.30
# PWV from RH/T: sat vapor density (g/m3) * RH * scale height
def sat_vapor_density(Tc):
    es = 6.112 * np.exp(17.67*Tc/(Tc+243.5))  # hPa
    return 216.7 * es / (Tc + 273.15)  # g/m3

rho_v = sat_vapor_density(T_AIR_C) * RH  # g/m3
H_SCALE = 2000.0
PWV_CM = rho_v * H_SCALE / 10000.0  # g/m2 -> cm water (1 cm water = 10 kg/m2 = 10000 g/m2)
print("actual plan weather: T=%.1fC RH=%.0f%% P=%.0fhPa vis=%.0fkm PWV=%0.2fcm" % (T_AIR_C, RH*100, P_HPA, VIS_KM, PWV_CM))

# aerosol extinction at 550 nm from visibility (Koschmieder); clean continental alpha
sigma_a550_km = 3.912 / VIS_KM  # km^-1 total extinction; assume aerosol part 0.9
sigma_a550_km *= 0.9

n_air_m3 = (P_HPA*100.0) / (KB*(T_AIR_C+273.15))
n_air_cm3 = n_air_m3 * 1e-6
col_h2o = PWV_CM * 3.345e22  # molecules/cm2

def atmos_for_slant(slant_km, t_air_C=T_AIR_C, pwv_cm=PWV_CM, vis_km=VIS_KM):
    arr = np.asarray(slant_km, dtype=float)
    scalar = arr.ndim == 0
    if scalar:
        arr = arr.reshape(1)
    s = arr[..., None]  # km
    R_cm = s * 1e5
    tau_aer = sigma_a550_km * (wl_um/0.55)**(-ALPHA) * s
    tau_h2o = xs("H2O") * col_h2o * (pwv_cm / PWV_CM)
    tau_co2 = xs("CO2") * n_air_cm3 * R_cm * (420e-6)
    tau_ch4 = xs("CH4") * n_air_cm3 * R_cm * (1.9e-6)
    tau_mol = 0.008735 * (0.55/wl_um)**4.08 * s
    tau = tau_aer + tau_h2o + tau_co2 + tau_ch4 + tau_mol
    T_air = t_air_C + 273.15
    L_path = np.trapezoid(planck_lam(T_air)*(1-np.exp(-tau)), wl_m, axis=-1)
    if scalar:
        return tau[0], float(L_path[0])
    return tau, L_path

# ---------- sensor & targets ----------
D_AP = 0.15
IFOV = np.deg2rad(3.75)/1024.0
LAM = 4.25e-6
NETD = 0.025
H_SENSOR = 8000.0
CN2 = 0.0  # plan: 不考虑湍流

TARGETS = [
    {"name": "F16战斗机", "dim": 14.85, "h_m": 500.0, "kind": "空中"},
    {"name": "F22战斗机", "dim": 18.60, "h_m": 500.0, "kind": "空中"},
    {"name": "尼米兹级航空母舰", "dim": 340.66, "h_m": 0.0, "kind": "海面"},
    {"name": "阿利伯克级驱逐舰", "dim": 151.32, "h_m": 0.0, "kind": "海面"},
    {"name": "悍马车", "dim": 5.09, "h_m": 10.0, "kind": "地面"},
    {"name": "爱国者导弹发射车", "dim": 22.57, "h_m": 10.0, "kind": "地面"},
]
T_BG_C = 20.0   # 与那国岛 Config.ini 环境温度
EPS_T = 0.90
EPS_B = 0.95
T_STATES = [(20.0, "20 °C"), (40.0, "40 °C"), (60.0, "60 °C")]
T_BG = T_BG_C + 273.15

def n_elem(theta_t, slant_km):
    R = slant_km*1000.0
    if CN2 > 0:
        r0 = (0.423*(2*np.pi/LAM)**2*CN2*R)**(-3/5)
    else:
        r0 = np.inf
    theta_diff = LAM/D_AP
    theta_eff = np.sqrt(theta_diff**2 + IFOV**2 + (LAM/r0 if np.isfinite(r0) else 0.0)**2)
    return theta_t/theta_eff, r0, theta_eff

def pd_task(ne, snr, nreq):
    p_res = 1.0/(1.0 + np.exp(-(ne-nreq)/1.2))
    p_con = 0.5*(1+math.erf((snr-3.0)/math.sqrt(2)))
    return p_res*p_con

GROUPS = np.linspace(1.0, 20.0, 77)
JOHNSON = {"detect": 4.0, "recognize": 16.0, "identify": 26.0}
rows = []
for tgt in TARGETS:
    for Tc, label in T_STATES:
        Tt = Tc + 273.15
        for dgr in GROUPS:
            dh = H_SENSOR - tgt["h_m"]
            slant = np.sqrt(dgr**2 + (dh/1000.0)**2)
            tau, Lp = atmos_for_slant(slant)
            Lt = np.trapezoid(EPS_T*planck_lam(Tt)*np.exp(-tau), wl_m) + Lp
            Lb = np.trapezoid(EPS_B*planck_lam(T_BG)*np.exp(-tau), wl_m) + Lp
            dT = t_app(Lt) - t_app(Lb)
            theta_t = tgt["dim"]/(slant*1000.0)
            ne, r0, te = n_elem(theta_t, slant)
            snr = (dT/NETD)*ne
            rows.append({
                "target": tgt["name"], "kind": tgt["kind"], "target_h_m": tgt["h_m"],
                "state": label, "ground_range_km": dgr, "slant_range_km": slant,
                "tau_band": float(np.trapezoid(np.exp(-tau), wl_m)/(wl_m[-1]-wl_m[0])),
                "L_path": Lp, "dT_app_K": dT, "theta_urad": theta_t*1e6,
                "Ne": ne, "r0_cm": r0*100 if np.isfinite(r0) else 0.0,
                "SNR": snr,
                "Pd_detect": pd_task(ne, snr, JOHNSON["detect"]),
                "Pd_recognize": pd_task(ne, snr, JOHNSON["recognize"]),
                "Pd_identify": pd_task(ne, snr, JOHNSON["identify"]),
            })

with open(os.path.join(OUT, "software_actual_case_results.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

# 50% distances for 40 C
summary = []
for tgt in TARGETS:
    sub = [r for r in rows if r["target"] == tgt["name"] and r["state"] == "40 °C"]
    sub.sort(key=lambda r: r["ground_range_km"])
    line = {"target": tgt["name"], "kind": tgt["kind"], "dim_m": tgt["dim"]}
    for key in ["Pd_detect", "Pd_recognize", "Pd_identify"]:
        vals = [r[key] for r in sub]; ds = [r["ground_range_km"] for r in sub]
        r50 = None
        for i in range(1, len(vals)):
            if vals[i-1] >= 0.5 and vals[i] < 0.5:
                r50 = ds[i-1] + (ds[i]-ds[i-1])*(vals[i-1]-0.5)/(vals[i-1]-vals[i])
                break
        line[key+"_50km"] = round(r50, 2) if r50 else None
    sub10 = [r for r in sub if abs(r["ground_range_km"]-10.0) < 0.01]
    if sub10:
        line["Ne_10km"] = round(sub10[0]["Ne"], 2)
        line["dT_10km"] = round(sub10[0]["dT_app_K"], 2)
    summary.append(line)

with open(os.path.join(OUT, "software_actual_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
    w.writeheader(); w.writerows(summary)
print(json.dumps(summary, ensure_ascii=False, indent=1))

# ---------- figures ----------
# Fig 1: tau, L_path vs slant range (ground target)
fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6), dpi=150)
old_colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
for h, lab, col in zip([0.0, 10.0, 500.0], ["海面目标", "地面目标", "空中目标"], old_colors):
    dh = H_SENSOR - h
    sl = np.sqrt(GROUPS**2 + (dh/1000.0)**2)
    tau, lp = atmos_for_slant(sl)
    tau_b = np.trapezoid(np.exp(-tau), wl_m, axis=-1)/(wl_m[-1]-wl_m[0])
    ax[0].plot(GROUPS, tau_b, lw=1.8, label=lab, color=col)
    ax[1].plot(GROUPS, lp, lw=1.8, label=lab, color=col)
ax[0].set_xlabel("地面距离（km）"); ax[0].set_ylabel("波段平均路径透过率")
ax[0].set_title("实际气象：3.7–4.8 μm 路径透过率", fontsize=11); ax[0].grid(alpha=.25)
ax[1].set_xlabel("地面距离（km）"); ax[1].set_ylabel("路径辐亮度（W/(m²·sr)）")
ax[1].set_title("实际气象：路径辐亮度", fontsize=11); ax[1].grid(alpha=.25)
for a in ax: a.legend(fontsize=8, frameon=False)
fig.suptitle("软件默认想定气象：15 °C / 50%RH / 10 km / 干净大陆 / 美国标准大气", fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "software_actual_atmos.png"), dpi=300)

# Fig 2: dT vs range for three target thermal states (F16, air target)
fig, ax = plt.subplots(figsize=(8.8, 4.8), dpi=150)
for Tc, label, col in [(20.0, "20 °C 低热", "#1f77b4"), (40.0, "40 °C 中热", "#ff7f0e"), (60.0, "60 °C 高热", "#d62728")]:
    sub = [r for r in rows if r["target"] == "F16战斗机" and r["state"] == label.replace(" 低热", "").replace(" 中热", "").replace(" 高热", "")]
    # state label in rows is "20 °C"/"40 °C"/"60 °C"
    key = f"{int(Tc)} °C"
    sub = [r for r in rows if r["target"] == "F16战斗机" and r["state"] == key]
    ax.plot([r["ground_range_km"] for r in sub], [r["dT_app_K"] for r in sub], lw=1.9, label=label, color=col)
ax.set_xlabel("地面距离（km）"); ax.set_ylabel("视在温差 ΔT_app（K）")
ax.set_title("软件实际气象/背景：F16 目标不同热状态下的视在温差", fontsize=12, fontweight="bold")
ax.grid(alpha=.3); ax.legend(fontsize=8, frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "software_actual_dt.png"), dpi=300)

# Fig 3: P_d recognition/identification vs range, 6 targets at 40C
colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.8), dpi=150, sharey=True)
for ax, key, title in [(axes[0], "Pd_recognize", "识别概率"), (axes[1], "Pd_identify", "辨认概率")]:
    for tgt, col in zip(TARGETS, colors):
        sub = [r for r in rows if r["target"] == tgt["name"] and r["state"] == "40 °C"]
        ax.plot([r["ground_range_km"] for r in sub], [r[key] for r in sub], lw=1.7, label=tgt["name"], color=col)
    ax.set_xlabel("地面距离（km）"); ax.set_title(title, fontsize=11); ax.grid(alpha=.25); ax.set_ylim(0, 1.02)
axes[0].set_ylabel("任务概率 P"); axes[0].legend(fontsize=7, frameon=False, loc="upper right")
fig.suptitle("软件实际目标模型 + 实际气象：任务概率随地面距离变化（40 °C 热状态）", fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "software_actual_pd.png"), dpi=300)

# Fig 4: 50% recognize/identify distances bar chart
fig, ax = plt.subplots(figsize=(9.6, 4.4), dpi=150)
x = np.arange(len(summary))
vals_r = [s["Pd_recognize_50km"] if s["Pd_recognize_50km"] is not None else 0 for s in summary]
vals_i = [s["Pd_identify_50km"] if s["Pd_identify_50km"] is not None else 0 for s in summary]
ax.bar(x-0.18, vals_r, 0.34, label="识别 50% 距离", color="#2c7fb8")
ax.bar(x+0.18, vals_i, 0.34, label="辨认 50% 距离", color="#e67e22")
ax.set_xticks(x); ax.set_xticklabels([s["target"] for s in summary], rotation=20, ha="right", fontsize=8)
ax.set_ylabel("地面距离（km）"); ax.set_title("软件实际目标模型的识别/辨认 50% 距离（40 °C 热状态）")
ax.grid(axis="y", alpha=.3); ax.legend(fontsize=8, frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "software_actual_50pct.png"), dpi=300)

print("figures saved")

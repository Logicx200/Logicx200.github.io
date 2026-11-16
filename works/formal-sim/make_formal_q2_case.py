# -*- coding: utf-8 -*-
"""Formal case study using XGGDCOSSim2 Q2 MWIR atmospheric LUT + user-defined IR sensor."""
import csv
import glob
import json
import math
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = r"F:\DeepSeek工作区\软件参数提取\Q2解析\atmosphere_data"
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

# ---------------- load Q2 MWIR ----------------
rows = []
for fn in sorted(glob.glob(os.path.join(BASE, "atmo_Q2M_b01_part*.csv"))):
    with open(fn, "r", encoding="utf-8-sig") as f:
        rows += list(csv.DictReader(f))
print("Q2 MWIR rows", len(rows))

def fnum(r, k):
    return float(r[k])

# sensor altitude 5000 m, azimuth 0, target height 500/1000 m
H_SENSOR = 5000.0
TARGET_HS = [500.0, 1000.0]
curves = {}
for th in TARGET_HS:
    sub = [r for r in rows if abs(fnum(r, "viewpoint_altitude_m") - H_SENSOR) < 1e-6
           and abs(fnum(r, "view_azimuth_deg")) < 1e-6
           and abs(fnum(r, "target_height_m") - th) < 1e-6]
    sub.sort(key=lambda r: fnum(r, "view_pitch_deg"))
    pitch = np.array([fnum(r, "view_pitch_deg") for r in sub])
    tau = np.array([fnum(r, "path_transmittance") for r in sub])
    lp = np.array([fnum(r, "path_radiance_W_m2sr") for r in sub])
    lb = np.array([fnum(r, "background_radiance_W_m2sr") for r in sub])
    sol = np.array([fnum(r, "solar_irradiance_W_m2") for r in sub])
    curves[th] = {"pitch": pitch, "tau": tau, "lp": lp, "lb": lb, "sol": sol}
    print("target h", th, "n", len(sub), "pitch", pitch.min(), pitch.max(),
          "tau range", tau.min(), tau.max())

# ---------------- Planck band radiance, 3.7-4.8 um ----------------
H_PL = 6.62607015e-34; C_LIGHT = 2.99792458e8; K_B = 1.380649e-23
wl = np.linspace(3.7, 4.8, 441) * 1e-6

def planck_band(T):
    B = 2*H_PL*C_LIGHT**2/wl**5 / np.expm1(H_PL*C_LIGHT/(wl*K_B*T))
    return np.trapezoid(B, wl)  # W/m2/sr

T_GRID = np.linspace(180.0, 450.0, 2701)
B_GRID = np.array([planck_band(T) for T in T_GRID])

def t_app(L):
    return np.interp(L, B_GRID, T_GRID)

# ---------------- sensor & geometry ----------------
D_AP = 0.15           # m
F_LEN = 0.45          # m
FOV_H_DEG = 3.75
DPI_H = 1024
IFOV = np.deg2rad(FOV_H_DEG) / DPI_H  # rad ~63.9 urad
NETD = 0.025          # K
LAM = 4.25e-6
CN2 = 1e-14
JOHNSON = {"detect": 4.0, "recognize": 16.0, "identify": 26.0}

def n_elem(theta_t, slant_km):
    R = slant_km * 1000.0
    r0 = (0.423 * (2*np.pi/LAM)**2 * CN2 * R) ** (-3/5)
    theta_eff = np.sqrt((LAM/r0)**2 + (LAM/D_AP)**2 + IFOV**2)
    return theta_t / theta_eff, r0, theta_eff

def pd_task(ne, snr, nreq):
    p_res = 1.0 / (1.0 + np.exp(-(ne - nreq) / 1.2))
    p_con = 0.5 * (1 + math.erf((snr - 3.0) / np.sqrt(2)))
    return p_res * p_con

# ---------------- target models ----------------
TARGETS = [
    {"name": "F16战斗机", "dim": 14.85, "kind": "空中"},
    {"name": "F22战斗机", "dim": 18.60, "kind": "空中"},
]
T_STATES = [
    {"name": "低热状态 20 °C", "T": 293.15, "eps": 0.90},
    {"name": "中热状态 40 °C", "T": 313.15, "eps": 0.90},
    {"name": "高热状态 60 °C", "T": 333.15, "eps": 0.90},
]

ranges = np.linspace(1.0, 20.0, 77)  # ground range km
res = []
for tgt in TARGETS:
    for th in TARGET_HS:
        cv = curves[th]
        for st in T_STATES:
            for DGR in ranges:
                dh = H_SENSOR - th
                slant_km = np.sqrt(DGR**2 + (dh/1000.0)**2)
                pitch = -np.degrees(np.arctan2(dh, DGR * 1000.0))
                tau = float(np.interp(pitch, cv["pitch"], cv["tau"]))
                lp = float(np.interp(pitch, cv["pitch"], cv["lp"]))
                lbg_q2 = float(np.interp(pitch, cv["pitch"], cv["lb"]))
                lint = st["eps"] * planck_band(st["T"])
                # 地面背景：同路径，背景温度取 Q2 大气条件 10 °C，发射率 0.95
                lbg = 0.95 * planck_band(283.15) * tau + lp
                l_t = lint * tau + lp
                ta = t_app(l_t) - t_app(lbg)
                theta_t = tgt["dim"] / (slant_km * 1000.0)
                ne, r0, te = n_elem(theta_t, slant_km)
                snr = (ta / NETD) * ne
                pd_d = pd_task(ne, snr, JOHNSON["detect"])
                pd_r = pd_task(ne, snr, JOHNSON["recognize"])
                pd_i = pd_task(ne, snr, JOHNSON["identify"])
                res.append({"target": tgt["name"], "target_h_m": th, "state": st["name"],
                            "ground_range_km": DGR, "slant_range_km": slant_km, "pitch_deg": pitch, "tau": tau,
                            "L_path": lp, "L_bg_Q2": lbg_q2, "L_bg_used": lbg, "dT_app_K": ta,
                            "theta_target_urad": theta_t*1e6, "r0_cm": r0*100, "Ne": ne,
                            "SNR": snr, "Pd_detect": pd_d, "Pd_recognize": pd_r, "Pd_identify": pd_i})

with open(os.path.join(OUT, "q2_case_results.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
    w.writeheader(); w.writerows(res)

print("dT range", min(r["dT_app_K"] for r in res), max(r["dT_app_K"] for r in res))
print("Ne range", min(r["Ne"] for r in res), max(r["Ne"] for r in res))
print("Pd rec range", min(r["Pd_recognize"] for r in res), max(r["Pd_recognize"] for r in res))

# ---------------- figures ----------------
# fig1: Q2 LUT tau / L vs slant range for th=500/1000
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), dpi=150)
for th in TARGET_HS:
    cv = curves[th]
    dh = H_SENSOR - th
    # map pitch -> slant range
    horiz = dh / np.tan(np.deg2rad(-cv["pitch"]))
    R = np.sqrt(horiz**2 + dh**2) / 1000.0
    axes[0].plot(R, cv["tau"], lw=1.8, label=f"目标高度 {int(th)} m")
    axes[1].plot(R, cv["lp"], lw=1.8, label=f"目标高度 {int(th)} m")
axes[0].set_xlabel("斜距 R（km）"); axes[0].set_ylabel("路径透过率 τ")
axes[0].set_title("Q2 大气数据：MWIR 3.7–4.8 μm 路径透过率"); axes[0].grid(True, alpha=.3)
axes[1].set_xlabel("斜距 R（km）"); axes[1].set_ylabel("路径辐亮度 L_path（W/(m²·sr)）")
axes[1].set_title("Q2 大气数据：路径辐亮度"); axes[1].grid(True, alpha=.3)
for ax in axes:
    ax.legend(fontsize=8, frameon=False)
fig.suptitle("软件内部 Q2 大气查找表（洛阳城市，10 °C/50%RH/25，传感器高度 5000 m）", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "q2_atmosphere_lut.png"), dpi=300)

# fig2: dT_app vs range for F16/F22, three states, h=500
fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=150, sharey=True)
colors = ["#2c7fb8", "#e67e22", "#c0392b"]
for ax, tgt in zip(axes, TARGETS):
    for k, st in enumerate(T_STATES):
        sub = [r for r in res if r["target"] == tgt["name"] and r["target_h_m"] == 500 and r["state"] == st["name"]]
        ax.plot([r["ground_range_km"] for r in sub], [r["dT_app_K"] for r in sub], lw=1.8, color=colors[k], label=st["name"])
    ax.set_xlabel("地面距离（km）"); ax.set_title(f"{tgt['name']}（目标高度 500 m）")
    ax.grid(True, alpha=.3); ax.legend(fontsize=8, frameon=False)
axes[0].set_ylabel("视在温差 ΔT_app（K）")
fig.suptitle("Q2 大气数据 + 目标模型：视在温差随地面距离变化（地面背景 10 °C）", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "q2_dt_vs_range.png"), dpi=300)

# fig3: P_d vs range for F16/F22, recognition/identification (state: working)
fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=150, sharey=True)
for ax, tgt in zip(axes, TARGETS):
    for task, key, ls in [("探测", "Pd_detect", "-"), ("识别", "Pd_recognize", "--"), ("辨认", "Pd_identify", ":")]:
        sub = [r for r in res if r["target"] == tgt["name"] and r["target_h_m"] == 500 and r["state"] == "中热状态 40 °C"]
        ax.plot([r["ground_range_km"] for r in sub], [r[key] for r in sub], lw=1.8, ls=ls, label=task)
    ax.set_xlabel("地面距离（km）"); ax.set_title(f"{tgt['name']}（中热状态 40 °C，目标高度 500 m）")
    ax.set_ylim(0, 1.02); ax.grid(True, alpha=.3); ax.legend(fontsize=8, frameon=False)
axes[0].set_ylabel("任务概率 P")
fig.suptitle("Q2 大气数据 + 传感器模型：任务概率随地面距离变化（C_n²=1e-14）", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "q2_pd_vs_range.png"), dpi=300)

print("figures saved to", OUT)

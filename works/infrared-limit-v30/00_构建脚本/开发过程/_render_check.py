# -*- coding: utf-8 -*-
"""按需重绘若干图件（草稿/回归检查用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

from irrecog import plots

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "00_构建脚本", "开发过程", "_draft_data")
FIG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "00_构建脚本", "开发过程", "_draft_figs")
which = sys.argv[3].split(",") if len(sys.argv) > 3 else ["04", "09", "13", "16", "17"]

sweeps = plots._clean_sweeps(DATA)
for w in which:
    if w == "04":
        plots.fig04_mtf_mrtd(FIG)
    elif w == "09":
        plots.fig09_thermal(FIG, sweeps, DATA)
    elif w == "13":
        plots.fig13_envelope(FIG, sweeps)
    elif w == "14":
        plots.fig14_phase_aod_cn2(FIG, DATA)
    elif w == "15":
        plots.fig15_phase_dt_aod(FIG, DATA)
    elif w == "16":
        plots.fig16_env_heatmap(FIG, DATA)
    elif w == "17":
        plots.fig17_sensitivity(FIG, sweeps)
    elif w == "12":
        plots.fig12_band(FIG, DATA)
    elif w == "01":
        plots.fig01_chain(FIG)
    elif w == "02":
        plots.fig02_environment_space(FIG)
    elif w == "05":
        plots.fig05_baseline_pd(FIG, DATA)
    elif w == "06":
        plots.fig06_tasks(FIG, sweeps)
    elif w == "07":
        plots.fig07_aod(FIG, sweeps)
    elif w == "08":
        plots.fig08_cn2(FIG, sweeps)
    elif w == "10":
        plots.fig10_sensor(FIG, sweeps)
    elif w == "11":
        plots.fig11_altitude(FIG, sweeps)
    else:
        print("unknown", w)
print("done", which)

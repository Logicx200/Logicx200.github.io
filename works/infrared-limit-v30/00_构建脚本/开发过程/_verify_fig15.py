# -*- coding: utf-8 -*-
"""用真实计算验证 图15（全 26 档 ΔT，AOD 取 4 档子集）与图06/12 版式。"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import numpy as np
from irrecog import experiments as E, plots

SM = os.path.join(ROOT, "00_构建脚本", "开发过程", "_smoke2")
FG = os.path.join(ROOT, "00_构建脚本", "开发过程", "_draft_figs2")

E.PHASE_AOD_DT = E.PHASE_AOD_DT[[0, 7, 14, 20]]
t0 = time.time()
df = E._phase_dt_aod(SM, verbose=True)
print(f"[timing] 相图 dT×AOD（4 AOD × 26 ΔT）{time.time()-t0:.1f}s, {len(df)} 行")
print(df.pivot_table(index="dT_K", columns="aod550", values="R50").to_string())

plots.fig06_tasks(FG, plots._clean_sweeps(SM))
plots.fig12_band(FG, SM)
plots.fig15_phase_dt_aod(FG, SM)
print("done")

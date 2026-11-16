# -*- coding: utf-8 -*-
"""最终一致性抽查：模型直算 vs 长表 vs 汇总表。"""
import os
import sys

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))
import numpy as np
import pandas as pd
from dataclasses import replace as _replace
from irrecog import chain

df = pd.read_csv(os.path.join(ROOT, "03_数据", "全工况长表", "eval_long.csv.gz"),
                 encoding="utf-8-sig", low_memory=False)
base = chain.baseline_scenario()

# 1) LWIR F16 @20 km
scn = _replace(base, sensor=_replace(base.sensor, band="LWIR"))
ev = chain.evaluate(scn, 20.0)
row = df[(df.sweep_id == "S02") & (df.band == "LWIR") & (df.target == "F16")]
row = row.iloc[(row.r_ground_km - 20.0).abs().argmin()]
print(f"LWIR F16@20: 模型 tau={ev['tau_band']:.6f} 长表={row['tau_band']:.6f} "
      f"偏差={abs(ev['tau_band']-row['tau_band']):.2e}")

# 2) MWIR 基线 F16 @10 km
ev = chain.evaluate(base, 10.0)
row = df[(df.sweep_id == "S01") & (df.target == "F16")]
row = row.iloc[(row.r_ground_km - 10.0).abs().argmin()]
print(f"MWIR F16@10: 模型 P_rec={ev['P_rec']:.6f} 长表={row['P_rec']:.6f}")

# 3) 汇总 vs 直算 R50
s = pd.read_csv(os.path.join(ROOT, "03_数据", "单变量对比", "S00_全扫描指标汇总.csv"),
                encoding="utf-8-sig")
r = s[(s.sweep_id == "S01") & (s.target == "F16")].iloc[0]
print(f"S01 F16 R50: 汇总={r['R50_ground_km']:.4f} km, eta={r['eta']:.4f}")

# 4) 报告文档中的图数量与页数
from docx import Document
d = Document(os.path.join(ROOT, "01_正式报告", "红外目标识别概率极限与临界状态_V3.0.docx"))
print(f"报告：图 {len(d.inline_shapes)} 幅，表 {len(d.tables)} 个，段落 {len(d.paragraphs)}")

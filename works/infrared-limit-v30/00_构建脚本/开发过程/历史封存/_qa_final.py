# -*- coding: utf-8 -*-
"""图件与数据最终 QA：文件齐全/有效/非空白、数据-图来源核对。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIG = os.path.join(ROOT, "02_图表")
DATA = os.path.join(ROOT, "03_数据")

import numpy as np
import pandas as pd
from PIL import Image

EXPECTED = [
    "图00_项目思维导图.png",
    "图01_模型链路与三类极限.png",
    "图02_工况空间与默认工况定位.png",
    "图03_斜程大气光谱透过率.png",
    "图04_MTF链与MRTD.png",
    "图05_基线任务概率曲线.png",
    "图06_三任务临界距离对比.png",
    "图07_单变量_气溶胶AOD.png",
    "图08_单变量_湍流Cn2.png",
    "图09_单变量_目标热状态与发射率.png",
    "图10_单变量_传感器参数.png",
    "图11_单变量_平台高度.png",
    "图12_波段对比.png",
    "图13_识别极限包络.png",
    "图14_相图_AODxCn2.png",
    "图15_相图_温差xAOD.png",
    "图16_真实气候工况热力图.png",
    "图17_敏感性弹性排序.png",
]

print("== 1) 图件齐全性与有效性 ==")
ok = True
for name in EXPECTED:
    p = os.path.join(FIG, name)
    if not os.path.exists(p):
        print(f"  [缺失] {name}")
        ok = False
        continue
    try:
        im = Image.open(p)
        arr = np.asarray(im.convert("L"), dtype=float)
        std = float(arr.std())
        dpi = im.info.get("dpi", ("?", "?"))
        flag = "OK" if std > 3.0 and min(im.size) > 500 else "可疑(可能空白)"
        if flag != "OK":
            ok = False
        print(f"  {flag:6s} {name:38s} {im.size[0]}x{im.size[1]} dpi={dpi} 灰度std={std:.1f}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [无法打开] {name}: {exc}")
        ok = False

print("\n== 2) 多余/旧编号文件检查 ==")
names = sorted(os.listdir(FIG))
stale = [n for n in names if n.startswith("图") and n.endswith(".png")
         and n not in EXPECTED and not n.startswith("图00_项目思维导图_横版")]
print("  图件目录全部文件:", names)
print("  非规范图件文件:", [n for n in names if n not in EXPECTED and not n.endswith(".csv")])
print("  旧编号残留:", stale if stale else "无")

print("\n== 3) 数据文件与行数 ==")
checks = [
    ("全工况长表/eval_long.csv.gz", 64800),
    ("单变量对比/S00_全扫描指标汇总.csv", 540),
    ("单变量对比/S01_目标类型.csv", 6),
    ("真实气候工况/环境工况_识别临界距离.csv", 144),
    ("临界状态/临界状态汇总.csv", 6),
    ("波段对比/波段对比_R50.csv", 228),
    ("相图/相图_AODxCn2.csv", 1050),
    ("相图/相图_dT_AOD.csv", 546),
]
for rel, expect in checks:
    p = os.path.join(DATA, rel)
    if not os.path.exists(p):
        print(f"  [缺失] {rel}")
        ok = False
        continue
    if rel.endswith(".gz"):
        df = pd.read_csv(p, encoding="utf-8-sig", usecols=[0, 1])
    else:
        df = pd.read_csv(p, encoding="utf-8-sig")
    flag = "OK" if len(df) == expect else f"行数异常(期望{expect})"
    if flag != "OK":
        ok = False
    print(f"  {flag:10s} {rel:42s} {len(df):6d} 行")
xlsx = os.path.join(DATA, "识别极限_数据汇总.xlsx")
if os.path.exists(xlsx):
    xl = pd.ExcelFile(xlsx)
    print(f"  OK        识别极限_数据汇总.xlsx                        {len(xl.sheet_names)} sheets")
else:
    print("  [缺失] XLSX")
    ok = False

print("\n== 4) 图-数据来源核对（抽样） ==")
s00 = pd.read_csv(os.path.join(DATA, "单变量对比", "S00_全扫描指标汇总.csv"), encoding="utf-8-sig")
s01 = s00[s00.sweep_id == "S01"].set_index("target")
print("  图05/13 数据源 S01：F16 R50=%.3f km（图13 标注应一致）；NIMITZ R50=%.2f km"
      % (float(s01.loc["F16", "R50_ground_km"]), float(s01.loc["NIMITZ", "R50_ground_km"])))
s12 = pd.read_csv(os.path.join(DATA, "波段对比", "波段对比_R50.csv"), encoding="utf-8-sig")
base = s12[(np.isclose(s12.aod550, 0.587)) & (np.isclose(s12.pwv_cm, 1.28))]
print("  图12 数据源 波段对比表：F16 MWIR=%.2f / LWIR=%.2f km"
      % (float(base[(base.target == "F16") & (base.band == "MWIR")].R50_ground_km.iloc[0]),
         float(base[(base.target == "F16") & (base.band == "LWIR")].R50_ground_km.iloc[0])))
p1 = pd.read_csv(os.path.join(DATA, "相图", "相图_AODxCn2.csv"), encoding="utf-8-sig")
print("  图14 数据源 相图表：%d 格（F16 %d / NIMITZ %d）"
      % (len(p1), (p1.target == "F16").sum(), (p1.target == "NIMITZ").sum()))
env = pd.read_csv(os.path.join(DATA, "真实气候工况", "环境工况_识别临界距离.csv"), encoding="utf-8-sig")
med = env[env["quantile"] == "median"].groupby("target")["R50_ground_km"].median()
print("  图16 数据源 环境表：NIMITZ 中位 R50=%.2f km（格内应与此一致）" % float(med["NIMITZ"]))

print("\n== 5) 版本字样检查（图件文件名） ==")
bad = [n for n in names if any(w in n for w in ("V1", "V2", "V3", "重构", "回填", "旧版", "上一版"))]
print("  含版本字样文件名:", bad if bad else "无")

print("\n总体:", "PASS" if ok else "FAIL")

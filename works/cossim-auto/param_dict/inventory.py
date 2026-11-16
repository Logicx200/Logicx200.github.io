# -*- coding: utf-8 -*-
"""盘点 V3.0 参数：登记表全部行 + 报告章节与表格。"""
import csv
import os
import sys

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
CSV = os.path.join(ROOT, "05_参数依据", "参数依据登记表.csv")
DOCX = os.path.join(ROOT, "01_正式报告", "红外目标识别概率极限与临界状态_V3.0.docx")

print("=" * 30, "参数登记表", "=" * 30)
rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
print("行数:", len(rows), "列:", list(rows[0].keys()))
from collections import Counter
print("\n类别分布:", dict(Counter(r["类别"] for r in rows)))
print("置信度分布:", dict(Counter(r["置信度"] for r in rows)))
print("\n---- 全部参数（精简） ----")
for i, r in enumerate(rows, 1):
    print(f"{i:3d} | {r['param_id']:<28} | {r['参数'][:26]:<26} | {r['符号'][:18]:<18} | "
          f"{r['取值'][:30]:<30} | {r['单位'][:10]:<10} | {r['类别']:<6} | {r['置信度']}")

print("\n" + "=" * 30, "报告章节/表格", "=" * 30)
try:
    from docx import Document
    doc = Document(DOCX)
    print("段落数:", len(doc.paragraphs), " 表格数:", len(doc.tables))
    print("\n---- 标题结构 ----")
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading") and p.text.strip():
            print(f"  [{p.style.name}] {p.text.strip()[:80]}")
    print("\n---- 表格概览 ----")
    for ti, t in enumerate(doc.tables, 1):
        hdr = " | ".join(c.text.strip().replace("\n", " ")[:18] for c in t.rows[0].cells)
        print(f"表{ti}: {len(t.rows)}行 x {len(t.columns)}列 | 表头: {hdr[:150]}")
except Exception as e:
    print("读取 docx 失败:", e)

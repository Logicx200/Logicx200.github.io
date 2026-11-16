# -*- coding: utf-8 -*-
"""导出参数明细（含依据说明摘要）与报告全部表格内容。"""
import csv
import os

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
CSV = os.path.join(ROOT, "05_参数依据", "参数依据登记表.csv")
DOCX = os.path.join(ROOT, "01_正式报告", "红外目标识别概率极限与临界状态_V3.0.docx")
OUT = r"F:\DeepSeek工作区\_cossim_auto\param_dict"
os.makedirs(OUT, exist_ok=True)

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
with open(os.path.join(OUT, "params_detail.txt"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(f"[{r['param_id']}] {r['参数']} | {r['符号']} = {r['取值']} {r['单位']} | "
                f"{r['类别']}/{r['置信度']}\n")
        f.write(f"  依据: {r['依据说明']}\n")
        f.write(f"  来源: {r['来源']}\n")
        f.write(f"  影响: {r['影响方向']}\n")
print("params_detail.txt 行数:", sum(1 for _ in open(os.path.join(OUT, "params_detail.txt"), encoding="utf-8")))

from docx import Document
doc = Document(DOCX)
with open(os.path.join(OUT, "report_tables.txt"), "w", encoding="utf-8") as f:
    for ti, t in enumerate(doc.tables, 1):
        f.write(f"\n===== 表{ti} ({len(t.rows)}行 x {len(t.columns)}列) =====\n")
        for row in t.rows:
            f.write(" | ".join(c.text.strip().replace("\n", " ") for c in row.cells) + "\n")
print("report_tables.txt 已写")
# 正文段落也导出（用于了解参数在报告中如何表述）
with open(os.path.join(OUT, "report_text.txt"), "w", encoding="utf-8") as f:
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            f.write(t + "\n")
print("report_text.txt 已写")

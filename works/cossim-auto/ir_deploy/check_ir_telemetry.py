# -*- coding: utf-8 -*-
"""检查 IR 仿真遥测与日志，确认辐射链路是否真正计算。"""
import glob, os

LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"

raw = open(LOG, "rb").read()
txt = raw.decode("gb18030", errors="replace")
lines = txt.splitlines()
# 取 23:17:40 之后的行
sel = [l for l in lines if l.startswith("[ 2026-11-03 23:17") or l.startswith("[ 2026-11-03 23:18")]
print("=== 23:17-23:18 日志中的 WARN/ERROR/辐射/热/大气 相关 ===")
hits = [l for l in sel if any(k in l for k in
        ("WARN", "ERROR", "错误", "失败", "辐射", "热", "大气", "透过率", "路径"))]
for l in hits[-25:]:
    print(" ", l.strip()[:170])
print("命中行数:", len(hits))

# 遥测 CSV
csvs = sorted(glob.glob(os.path.join(RT, "CsvData", "*.csv")), key=os.path.getmtime)
print("\n=== 最新遥测 CSV ===")
print(os.path.basename(csvs[-1]), os.path.getsize(csvs[-1]), "B")
txt2 = open(csvs[-1], "rb").read().decode("gb18030", errors="replace")
rows = txt2.splitlines()
print("行数:", len(rows))
print("表头:", rows[0][:260])
print("数据首行:", rows[1][:260] if len(rows) > 1 else "")
# 解析 Atmo_0..3 列（表头第 16-19 列，1-based）
hdr = rows[0].split(",")
idx = [i for i, h in enumerate(hdr) if "Atmo_" in h or "RenderFrame" in h]
print("\n关键列:", [(i, hdr[i][:40]) for i in idx])
vals = rows[1].split(",")
for i in idx:
    print(f"  {hdr[i][:50]} = {vals[i]}")

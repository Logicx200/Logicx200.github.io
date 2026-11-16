# -*- coding: utf-8 -*-
"""
一键重建：数据 → 图件 → 汇总表 → 报告（DOCX/PDF）

用法（在项目根目录）：
    python run_all.py             # 全量
    python run_all.py --data      # 只重算数据
    python run_all.py --plots     # 只重画图件
    python run_all.py --report    # 只重建报告
    python run_all.py --pdf       # 只导出 PDF
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "04_模型代码"))

import pandas as pd  # noqa: E402

from irrecog import experiments as E  # noqa: E402
from irrecog import plots  # noqa: E402

REPORT_NAME = "红外目标识别概率极限与临界状态_仿真报告"


def build_data():
    data = os.path.join(ROOT, "03_数据")
    t0 = time.time()
    print("[1/3] 单变量扫描 ...", flush=True)
    res = E.run_all(data)
    print("[2/3] 真实气候工况 ...", flush=True)
    env = E.run_environments(data)
    print("[3/3] 临界状态反解 ...", flush=True)
    crit = E.run_critical_states(data)
    print(f"数据完成：长表 {len(res['long'])} 行，扫描汇总 {len(res['summary'])} 行，"
          f"环境工况 {len(env)} 行，临界状态 {len(crit)} 行；耗时 {time.time()-t0:.0f} s", flush=True)
    return res, env, crit


def build_plots():
    plots.make_all(os.path.join(ROOT, "03_数据"), os.path.join(ROOT, "02_图表"))


def build_mindmap():
    """项目思维导图（00_构建脚本/make_mindmap.py 独立生成）。"""
    script = os.path.join(ROOT, "00_构建脚本", "make_mindmap.py")
    if not os.path.exists(script):
        print("[跳过] 缺少 00_构建脚本/make_mindmap.py", flush=True)
        return None
    print("生成思维导图 ...", flush=True)
    subprocess.run([sys.executable, script], cwd=ROOT, check=False)
    return os.path.join(ROOT, "02_图表", "图00_项目思维导图.png")


def build_workbook():
    """把全部数据表汇总成 XLSX（每类单变量一个 sheet，便于直接对比）。"""
    data = os.path.join(ROOT, "03_数据")
    out = os.path.join(data, "识别极限_数据汇总.xlsx")
    sheets = {}
    sweep_dir = os.path.join(data, "单变量对比")
    if os.path.isdir(sweep_dir):
        for fn in sorted(os.listdir(sweep_dir)):
            if fn.endswith(".csv"):
                key = fn[:-4][:31]
                sheets[key] = pd.read_csv(os.path.join(sweep_dir, fn), encoding="utf-8-sig")
    for sub, pat in (("真实气候工况", "环境工况_识别临界距离.csv"),
                     ("临界状态", "临界状态汇总.csv"),
                     ("波段对比", "波段对比_R50.csv"),
                     ("相图", "相图_AODxCn2.csv"),
                     ("相图", "相图_dT_AOD.csv")):
        p = os.path.join(data, sub, pat)
        if os.path.exists(p):
            sheets[f"{sub}_{pat[:-4]}"[:31]] = pd.read_csv(p, encoding="utf-8-sig")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    print("workbook ->", out, f"({len(sheets)} sheets)", flush=True)
    return out


def build_report():
    from irrecog import report
    out = os.path.join(ROOT, "01_正式报告", REPORT_NAME + ".docx")
    report.build(os.path.join(ROOT, "03_数据"), os.path.join(ROOT, "02_图表"), out)
    return out


def build_pdf():
    """用 Word COM 把 DOCX 导出为同名 PDF。"""
    docx = os.path.join(ROOT, "01_正式报告", REPORT_NAME + ".docx")
    pdf = os.path.join(ROOT, "01_正式报告", REPORT_NAME + ".pdf")
    if not os.path.exists(docx):
        print("[跳过] 缺少 DOCX，无法导出 PDF", flush=True)
        return None
    script = os.path.join(ROOT, "00_构建脚本", "export_pdf.ps1")
    if not os.path.exists(script):
        print("[跳过] 缺少 00_构建脚本/export_pdf.ps1", flush=True)
        return None
    print("导出 PDF ...", flush=True)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", script, "-In", docx, "-Out", pdf], check=False)
    return pdf if os.path.exists(pdf) else None


def main():
    args = set(a for a in sys.argv[1:] if a.startswith("--"))
    tasks = {
        "data": build_data,
        "plots": build_plots,
        "mindmap": build_mindmap,
        "xlsx": build_workbook,
        "report": build_report,
        "pdf": build_pdf,
    }
    todo = [k for k in ("data", "plots", "mindmap", "xlsx", "report", "pdf")
            if (f"--{k}" in args)]
    if not args:
        todo = ["data", "plots", "mindmap", "xlsx", "report", "pdf"]
    for k in todo:
        print(f"===== {k} =====", flush=True)
        tasks[k]()
    print("全部完成", flush=True)


if __name__ == "__main__":
    main()

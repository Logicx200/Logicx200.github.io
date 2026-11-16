# -*- coding: utf-8 -*-
"""交付收尾：整理开发脚本、生成文件清单、更新接口约定双通道说明。"""
import os
import shutil
import sys

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
BUILD = os.path.join(ROOT, "00_构建脚本")
DEV = os.path.join(BUILD, "开发过程")
os.makedirs(DEV, exist_ok=True)

# 1) 把开发期临时脚本归档，保留 fetch_hitran_all.py
keep = {"fetch_hitran_all.py", "接口约定.md"}
moved = []
for fn in os.listdir(BUILD):
    p = os.path.join(BUILD, fn)
    if os.path.isfile(p) and fn not in keep:
        shutil.move(p, os.path.join(DEV, fn))
        moved.append(fn)
print("归档开发脚本:", len(moved))

# 2) 清理 __pycache__
for dirpath, dirnames, _ in os.walk(ROOT):
    for d in list(dirnames):
        if d == "__pycache__":
            shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
            dirnames.remove(d)

# 3) 文件清单
rows = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "_hapi_db", "_xsect_parts")]
    for fn in filenames:
        if fn in ("文件清单.csv",):
            continue
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, ROOT)
        rows.append((rel, os.path.getsize(fp)))
rows.sort(key=lambda x: x[0])
out = os.path.join(ROOT, "文件清单.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    f.write('"相对路径","大小KB"\n')
    for rel, size in rows:
        f.write(f'"{rel}","{size/1024:.1f}"\n')
print("文件数:", len(rows), "->", out)
total = sum(s for _, s in rows)
print(f"总大小 {total/1024/1024:.1f} MB")

# -*- coding: utf-8 -*-
"""S0 动态探针：给大气数据文件字段填假文件，跑仿真准备，用日志反推格式。"""
import os
import re

ROOT = r"D:\XGGDCOSSim2"
WS = os.path.join(ROOT, "Data", "WorkSpaceFile")
SRC_PLAN = os.path.join(WS, "Anchor_F16_yngd.xml")
OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PROBE = os.path.join(OUT, "probe")
os.makedirs(PROBE, exist_ok=True)

# 1) 假数据文件（先给 1 列 1 行）
DUMMY1 = os.path.join(PROBE, "band1_probe.csv")
open(DUMMY1, "w", encoding="utf-8").write("1\n")
print("假文件:", DUMMY1)

# 2) 基于现有想定生成探针想定
s = open(SRC_PLAN, "rb").read().decode("gb18030", errors="replace")
print("源想定大小:", len(s), "字符")
print("源想定中的大气相关字段:")
for key in ("TranRadAtmModelFile", "LaserAtmModelFile", "BandAtmTranRadFile",
            "Band2AtmTranRadFile", "ImagBand1Class"):
    m = re.search(rf'<{key}[^>]*value="([^"]*)"', s)
    print(f"  {key} = {m.group(1) if m else '未找到'}")

s2 = s
s2 = re.sub(r'(<BandAtmTranRadFile[^>]*value=")[^"]*(")',
            lambda m: m.group(1) + DUMMY1 + m.group(2), s2)
s2 = re.sub(r'(<TranRadAtmModelFile[^>]*value=")[^"]*(")',
            lambda m: m.group(1) + os.path.join(PROBE, "atm_card_probe.dat") + m.group(2), s2)
open(os.path.join(PROBE, "atm_card_probe.dat"), "w").write("0\n")

dst = os.path.join(WS, "_probe_atmo.xml")
open(dst, "wb").write(s2.encode("gb18030"))
print("探针想定:", dst, os.path.getsize(dst), "B")

# 校验
back = open(dst, "rb").read().decode("gb18030", errors="replace")
for key in ("TranRadAtmModelFile", "BandAtmTranRadFile"):
    m = re.search(rf'<{key}[^>]*value="([^"]*)"', back)
    print(f"  回读 {key} = {m.group(1) if m else '未找到'}")

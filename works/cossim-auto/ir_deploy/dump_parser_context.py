# -*- coding: utf-8 -*-
"""在 DLL 中定位字段名，并打印其前后 ASCII 字符串上下文，寻找格式/扩展名线索。"""
import os
import re

BIN = r"D:\XGGDCOSSim2\bin"
PLUG = os.path.join(BIN, "plugins")
TARGETS = ["XGData.dll", "XGSchedule.dll", "XGScenes.dll",
           "libcossim_environment_ui.dll", "libcossim_prepare_ui.dll", "XGCOSSimUI.dll"]
KEYS = [b"BandAtmTranRadFile", b"TranRadAtmModelFile", b"LaserAtmModelFile"]

for name in TARGETS:
    fp = os.path.join(BIN, name)
    if not os.path.exists(fp):
        fp = os.path.join(PLUG, name)
    if not os.path.exists(fp):
        continue
    b = open(fp, "rb").read()
    print(f"\n===== {name} ({len(b):,} B) =====")
    for kw in KEYS:
        i = b.find(kw)
        if i < 0:
            continue
        print(f"\n-- {kw.decode()} @ {i} --")
        seg = b[max(0, i - 800):i + 800]
        # 抽出连续可打印 ASCII 串
        toks = re.findall(rb"[\x20-\x7e]{4,}", seg)
        toks = [t.decode("ascii", "ignore") for t in toks]
        for t in toks[:60]:
            print("   ", t[:120])

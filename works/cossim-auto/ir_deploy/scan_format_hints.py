# -*- coding: utf-8 -*-
"""在 XGGDCOSSim 的 DLL 里搜 MODTRAN/大气数据文件格式线索（纯 ASCII 词）。"""
import os
import glob
import re

BIN = r"D:\XGGDCOSSim2\bin"
PLUG = os.path.join(BIN, "plugins")
KEYS = ["tape5", "tape6", "tape7", "tp5", "tp6", "tp7", "MODTRAN", "Modtran", "modtran",
        "AFGL", "atm_", "Atmo", "ATM", "radiance", "transmittance", "TranRad", "BandAtm",
        "TranRadAtmModelFile", "BandAtmTranRadFile", ".tp", ".atm", ".rt", ".dat"]
files = glob.glob(os.path.join(PLUG, "*.dll")) + glob.glob(os.path.join(BIN, "*.dll")) + \
        glob.glob(os.path.join(BIN, "*.exe"))
hits = {}
for fp in files:
    try:
        b = open(fp, "rb").read()
    except Exception:
        continue
    found = []
    for k in KEYS:
        if k.encode() in b:
            found.append(k)
    if found:
        hits[os.path.basename(fp)] = found
for fn in sorted(hits, key=lambda x: -len(hits[x])):
    print(f"{fn}: {', '.join(hits[fn])}")

# 在 XGSchedule / XGScenes / environment_ui 里抽取含 keyword 的 ASCII 字符串上下文
print("\n=== 上下文片段 ===")
TARGETS = ["XGSchedule.dll", "XGScenes.dll", "libcossim_environment_ui.dll", "XGData.dll"]
for t in TARGETS:
    fp = os.path.join(BIN, t)
    if not os.path.exists(fp):
        fp = os.path.join(PLUG, t)
    if not os.path.exists(fp):
        continue
    b = open(fp, "rb").read()
    print(f"\n--- {t} ---")
    for kw in (b"TranRad", b"BandAtm", b"MODTRAN", b"tape5", b"AFGL", b"radiance"):
        start = 0
        cnt = 0
        while cnt < 4:
            i = b.find(kw, start)
            if i < 0:
                break
            seg = b[max(0, i - 70):i + 110]
            seg = re.sub(rb"[^\x20-\x7e]", b".", seg).decode("ascii", "ignore")
            print(f"  [{kw.decode()}] ...{seg}...")
            start = i + 1
            cnt += 1

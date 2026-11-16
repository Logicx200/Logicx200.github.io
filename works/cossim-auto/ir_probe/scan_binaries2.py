# -*- coding: utf-8 -*-
"""重扫二进制：UTF-8 / UTF-16LE / GB18030 三种编码。"""
import os
import glob

BIN = r"D:\XGGDCOSSim2\bin"
PLUG = os.path.join(BIN, "plugins")
KEYS = ["中波红外", "长波红外", "短波红外", "红外传感器", "热特性", "热物性", "温度场",
        "辐亮度", "发射率", "大气模型", "MODTRAN", "Modtran", "大气透过率", "路径辐射",
        "传感器类型", "可见光", "波段", "热辐射", "辐射源"]
files = glob.glob(os.path.join(PLUG, "*.dll")) + glob.glob(os.path.join(BIN, "*.dll")) + \
        glob.glob(os.path.join(BIN, "*.exe")) + glob.glob(os.path.join(BIN, "osgPlugins-3.6.5", "*.dll"))
print("文件数:", len(files))
hits = {}
for fp in files:
    try:
        b = open(fp, "rb").read()
    except Exception:
        continue
    found = set()
    for k in KEYS:
        for enc in ("utf-8", "utf-16-le", "gb18030"):
            try:
                if k.encode(enc) in b:
                    found.add(f"{k}[{enc}]")
                    break
            except Exception:
                pass
    if found:
        hits[os.path.basename(fp)] = sorted(found)
for fn in sorted(hits, key=lambda x: -len(hits[x])):
    print(f"\n{fn}:")
    print("   ", ", ".join(hits[fn]))
print("\n命中文件数:", len(hits))

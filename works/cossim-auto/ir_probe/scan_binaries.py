# -*- coding: utf-8 -*-
"""探测 XGGDCOSSim 二进制与资源里是否有红外/热模型实现（字节包含判断，不用正则）。"""
import os
import glob

BIN = r"D:\XGGDCOSSim2\bin"
PLUG = os.path.join(BIN, "plugins")
KEYS = ["中波红外", "长波红外", "短波红外", "红外", "热特性", "热物性", "温度场",
        "辐射率", "发射率", "辐亮度", "大气模型", "MODTRAN", "Modtran", "CART",
        "SensorType", "Thermal", "MWIR", "LWIR", "Emissiv", "irradiance"]

files = glob.glob(os.path.join(PLUG, "*.dll")) + \
        glob.glob(os.path.join(BIN, "*.dll")) + \
        glob.glob(os.path.join(BIN, "*.exe")) + \
        glob.glob(os.path.join(BIN, "osgPlugins-3.6.5", "*.dll"))
print("待扫描文件:", len(files))
hits = {}
for fp in files:
    try:
        b = open(fp, "rb").read()
    except Exception:
        continue
    found = []
    for k in KEYS:
        if k.isascii():
            if k.encode("ascii") in b:
                found.append(k)
        else:
            if k.encode("gb18030") in b:
                found.append(k + "[gb]")
            elif k.encode("utf-16-le") in b:
                found.append(k + "[u16]")
    if found:
        hits[os.path.basename(fp)] = sorted(set(found))

print("\n=== 命中文件 ===")
for fn in sorted(hits, key=lambda x: -len(hits[x])):
    print(f"{fn}:")
    print("   ", ", ".join(hits[fn]))

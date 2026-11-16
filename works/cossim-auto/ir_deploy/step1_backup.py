# -*- coding: utf-8 -*-
"""Step 1: 备份关键文件并检查编码/结构。"""
import os
import shutil
import datetime

SRC_DB = r"D:\XGGDCOSSim2\Data\SystemBaseFile\ModelDatabase.xml"
SRC_CFG = r"D:\XGGDCOSSim2\Data\config\pluginMgr\plugin_prepare_cfg.ini"
OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
os.makedirs(OUT, exist_ok=True)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
for src, tag in ((SRC_DB, "ModelDatabase"), (SRC_CFG, "plugin_prepare_cfg")):
    dst = os.path.join(OUT, f"{tag}.bak_{ts}")
    shutil.copy2(src, dst)
    print(f"备份: {dst}  ({os.path.getsize(dst):,} bytes)")

# 编码与结构检查
for p in (SRC_DB, SRC_CFG):
    b = open(p, "rb").read()
    print(f"\n=== {os.path.basename(p)} ===")
    print("  size:", len(b), " BOM:", b[:3].hex())
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            t = b.decode(enc)
            print(f"  用 {enc} 解码成功，含 '可见光': {'可见光' in t}, 含 'SensorModel': {'SensorModel' in t}")
            break
        except Exception as e:
            print(f"  用 {enc} 解码失败: {e}")

# ModelDatabase 传感器段边界
t = open(SRC_DB, "rb").read().decode("utf-8")
i0 = t.find("<SensorModel")
i1 = t.find("</SensorModel>")
print(f"\nSensorModel 段: {i0} .. {i1}，长度 {i1-i0}")
print("段落首 240 字:")
print(t[i0:i0+240])
print("段落尾 200 字:")
print(t[i1-200:i1])

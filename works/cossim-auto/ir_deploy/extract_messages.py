# -*- coding: utf-8 -*-
"""从 XGData/XGSchedule 抽取中文/英文提示串，找大气数据文件格式线索。"""
import os
import re

BIN = r"D:\XGGDCOSSim2\bin"
PLUG = os.path.join(BIN, "plugins")
TARGETS = ["XGData.dll", "XGSchedule.dll", "libcossim_environment_ui.dll",
           "libcossim_prepare_ui.dll", "XGCOSSimUI.dll"]
KW_CN = ["大气", "辐射", "透过率", "格式", "文件", "路径", "错误", "失败", "读取", "解析",
         "行数", "列数", "波段", "波长", "辐亮度", "温度"]
KW_EN = ["TranRad", "BandAtm", "atmo", "Atmo", "radiance", "transmitt", "MODTRAN", "card",
         "tape", ".rt", ".dat", ".csv", ".txt", "format", "parse"]

for name in TARGETS:
    fp = os.path.join(BIN, name)
    if not os.path.exists(fp):
        fp = os.path.join(PLUG, name)
    if not os.path.exists(fp):
        continue
    b = open(fp, "rb").read()
    print(f"\n===== {name} ({len(b):,} B) =====")

    # 提取 UTF-8 中文串（连续中文+常见标点/数字）
    try:
        t = b.decode("utf-8", errors="ignore")
    except Exception:
        t = ""
    cn = re.findall(r"[\u4e00-\u9fff][\u4e00-\u9fff0-9A-Za-z_，。：、（）()/%·\-\.\s]{2,60}", t)
    cn = [s.strip() for s in cn]
    hits = [s for s in cn if any(k in s for k in KW_CN)]
    seen = set()
    print(f"  中文候选 {len(hits)} 条：")
    for s in hits:
        if s in seen or len(s) < 4:
            continue
        seen.add(s)
        print("   ", s[:80])

    # 英文串
    en = re.findall(rb"[\x20-\x7e]{6,}", b)
    enhits = []
    for e in en:
        s = e.decode("ascii", "ignore")
        if any(k in s for k in KW_EN):
            enhits.append(s)
    uniq = []
    seen2 = set()
    for s in enhits:
        if s not in seen2:
            seen2.add(s); uniq.append(s)
    print(f"  英文候选 {len(uniq)} 条（前 30）：")
    for s in uniq[:30]:
        print("   ", s[:110])

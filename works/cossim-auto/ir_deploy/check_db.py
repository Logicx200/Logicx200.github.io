# -*- coding: utf-8 -*-
"""检查 ModelDatabase.xml 合法性与传感器条目，并对比 DefaultModelDatabase。"""
import os
import xml.etree.ElementTree as ET

DB = r"D:\XGGDCOSSim2\Data\SystemBaseFile\ModelDatabase.xml"
DEFAULT_DB = r"D:\XGGDCOSSim2\Data\SystemBaseFile\DefaultModelDatabase.xml"
BAK = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy\ModelDatabase.bak_20261103_231116"

for p in (BAK, DB, DEFAULT_DB):
    print(f"\n=== {os.path.basename(p)} ({os.path.getsize(p):,} B) ===")
    try:
        tree = ET.parse(p)
        root = tree.getroot()
        sensors = root.findall(".//SubSensorInfo")
        print("  XML 合法；SubSensorInfo 数量:", len(sensors))
        for s in sensors:
            st = s.find("SensorType")
            pn = s.find("ProductName")
            print(f"    Id={s.get('Id')} SensorType={st.get('value') if st is not None else '?'} "
                  f"ProductName={pn.get('value') if pn is not None else '?'}")
    except ET.ParseError as e:
        print("  XML 解析失败:", e)

# 当前 DB 中传感器段原始文本（确认插入位置）
t = open(DB, "rb").read().decode("utf-8")
i0, i1 = t.find("<SensorModel"), t.find("</SensorModel>")
seg = t[i0:i1]
print("\n当前 SensorModel 段长度:", len(seg))
print("段内 SubSensorInfo 数:", seg.count("<SubSensorInfo"))
print("我们的条目是否含 tips 拼写错误:", "tabs=" in seg)

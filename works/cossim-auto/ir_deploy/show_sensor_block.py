# -*- coding: utf-8 -*-
"""查看想定中传感器与传感器效应两段的完整字段。"""
P = r"F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\05_软件参数提取\_decoded\Data__SystemBaseFile__DefaultPlanFile.xml.utf8.txt"
lines = open(P, encoding="utf-8").read().split("\n")
for i in range(184, 268):
    t = lines[i].strip()
    if t:
        print(f"{i+1:4d}: {t[:170]}")

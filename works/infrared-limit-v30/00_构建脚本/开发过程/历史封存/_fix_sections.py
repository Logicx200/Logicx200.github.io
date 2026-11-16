# -*- coding: utf-8 -*-
"""修正第 4 章小节编号（4.2 相图已移入第 3 章）。"""
PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
s = open(PATH, encoding="utf-8").read()
s = s.replace('"4.3  热交叉识别盲区（临界温差）"', '"4.2  热交叉识别盲区（临界温差）"')
s = s.replace('"4.4  临界气溶胶、湍流与传感器极限"', '"4.3  临界气溶胶、湍流与传感器极限"')
open(PATH, "w", encoding="utf-8").write(s)
compile(s, PATH, "exec")
print("ok")

# -*- coding: utf-8 -*-
"""针对 report.py 剩余个别位置做精确替换，并反复语法检查。"""
import re
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"

src = open(PATH, encoding="utf-8").read()
# 通用：紧邻 }) 的中文引号一定是 Python 定界符
src = re.sub(r'[“”](?=\}\)?)', '"', src)
# 通用：紧邻 ,“ 或 ,” 前后为 ASCII 的代码分隔场景
src = re.sub(r'(?<=[,(=])[“”]', '"', src)
open(PATH, "w", encoding="utf-8").write(src)
try:
    compile(src, PATH, "exec")
    print("语法检查通过")
except SyntaxError as e:
    ls = src.split("\n")
    print("语法错误:", e.lineno, e.msg)
    for i in range(max(0, e.lineno - 3), min(len(ls), e.lineno + 2)):
        print(i + 1, repr(ls[i])[:260])
    sys.exit(1)

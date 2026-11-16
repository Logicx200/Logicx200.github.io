# -*- coding: utf-8 -*-
"""report.py 引号最终收敛：反替换（带上下文约束）+ 收尾修复 + 语法检查。"""
import re
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"


def cjkish(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF) or (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF) \
        or (0x2000 <= o <= 0x206F)


def restore(line: str) -> str:
    out = []
    n = len(line)
    for i, ch in enumerate(line):
        if ch in "“”":
            prev = line[i - 1] if i > 0 else ""
            nxt = line[i + 1] if i + 1 < n else ""
            if ch == "“" and not cjkish(prev) and not cjkish(nxt):
                out.append('"')
                continue
            if ch == "”" and not cjkish(prev) and not cjkish(nxt):
                out.append('"')
                continue
        out.append(ch)
    return "".join(out)


src = open(PATH, encoding="utf-8").read()
lines = src.split("\n")
in_doc = False
out = []
for line in lines:
    if line.count('"""') % 2 == 1:
        in_doc = not in_doc
        out.append(line)
        continue
    if in_doc:
        out.append(line)
        continue
    out.append(restore(line))
src = "\n".join(out)

# 收尾：汉字后紧跟的两个 ASCII 引号 —— 前者是中文收尾引号
src = re.sub(r'(?<=[\u4e00-\u9fff])"(?=")', "”", src)
# 汉字后紧跟 、`,)` 前的 ASCII 引号 —— 内容收尾
src = re.sub(r'(?<=[\u4e00-\u9fff])"(?=[，。；、：）])', "”", src)
# 汉字后紧跟汉字/全角标点的 ASCII 引号 —— 内容引号（奇偶交替交给后续人工确认，这里先统一为收尾）
src = re.sub(r'(?<=[\u4e00-\u9fff])"(?=[\u4e00-\u9fff])', "”", src)

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

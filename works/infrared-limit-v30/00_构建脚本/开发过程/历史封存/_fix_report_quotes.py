# -*- coding: utf-8 -*-
"""把 report.py 中被误用为中文引号的 ASCII 双引号替换为 “ ”，然后做语法检查（v2：带方向判定）。"""
import re
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
CJK = r"\u4e00-\u9fff"
NEXT_OK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u2000-\u206f"
PAT = re.compile(rf'(?<=[{CJK}])"(?=[{NEXT_OK}])')
CLOSING = set("。，；、：）】」』”…！？—～·")
OPENING = set("（【「『“")


def make_rep():
    state = {"expect": "“"}

    def rep(m):
        s = m.string
        nxt = s[m.end()] if m.end() < len(s) else ""
        if nxt in CLOSING:
            return "”"
        ch = state["expect"]
        state["expect"] = "”" if ch == "“" else "“"
        return ch
    return rep


src = open(PATH, encoding="utf-8").read()
lines = src.split("\n")
out = []
cnt = 0
for line in lines:
    new_line = PAT.sub(make_rep(), line)
    cnt += sum(1 for a, b in zip(line, new_line) if a == '"' and b in "“”") if len(line) == len(new_line) else 0
    out.append(new_line)
new = "\n".join(out)
# 补充规则：内容收尾引号紧跟字符串结束引号（形如 ...距离"" ）
new = re.sub(r'(?<=[\u4e00-\u9fff])"(?=")', "”", new)
# 统计替换数（粗略）
n_ascii_before = src.count('"')
open(PATH, "w", encoding="utf-8").write(new)
print("替换后 ASCII 双引号数量：", new.count('"'), "（原", n_ascii_before, "）")

try:
    compile(new, PATH, "exec")
    print("语法检查通过")
except SyntaxError as e:
    print("语法错误:", e.lineno, e.msg)
    ls = new.split("\n")
    for i in range(max(0, e.lineno - 2), min(len(ls), e.lineno + 1)):
        print(i + 1, repr(ls[i])[:240])
    sys.exit(1)

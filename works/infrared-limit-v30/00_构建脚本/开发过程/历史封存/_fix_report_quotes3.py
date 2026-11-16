# -*- coding: utf-8 -*-
"""report.py 引号修复器 v3：用状态机区分 Python 字符串定界符与中文引号。

规则
----
* 行内含 \"\"\" → 视为文档字符串，原样通过；
* 不在字符串内时，遇 '\"'：若前一个非空字符属于 ( , = [ { + : 或为 f/r/b/u 前缀或行首，
  则该 \" 是字符串起始定界符（保留）；否则视为中文引号左引号（换成 “）；
* 在字符串内时，遇 '\"'：若下一个字符属于 ) , ] + : ; 空白 行尾 或与另一个 \" 组成结束定界，
  则为结束定界符（保留）；否则视为中文引号（按本字符串内第 1/3/5… 个 → “，第 2/4/6… 个 → ”）。
"""
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
START_PREV = set("(,=[{+: \t")
PREFIX = set("frbuFRBU")
END_NEXT = set("),]+:; }\t")


def fix_line(line: str) -> str:
    out = []
    in_str = False
    qcount = 0
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch != '"':
            out.append(ch)
            i += 1
            continue
        if not in_str:
            j = len("".join(out).rstrip())
            prev = "".join(out).rstrip()[-1] if j > 0 else ""
            is_start = (j == 0) or (prev in START_PREV) or (prev in PREFIX and (j < 2 or "".join(out).rstrip()[-2] in START_PREV))
            if is_start:
                in_str = True
                qcount = 0
                out.append(ch)
            else:
                out.append("“")
            i += 1
            continue
        # in string
        nxt = line[i + 1] if i + 1 < n else ""
        if nxt == '"':
            nxt2 = line[i + 2] if i + 2 < n else ""
            if nxt2 == "" or nxt2 in END_NEXT:
                out.append("”")
                out.append('"')
                in_str = False
                i += 2
                continue
        ends = (nxt == "") or (nxt in END_NEXT)
        if ends:
            out.append(ch)
            in_str = False
            i += 1
            continue
        qcount += 1
        out.append("“" if qcount % 2 == 1 else "”")
        i += 1
    return "".join(out)


def main():
    lines = open(PATH, encoding="utf-8").read().split("\n")
    out = []
    in_doc = False
    changed = 0
    for line in lines:
        if line.count('"""') % 2 == 1:
            in_doc = not in_doc
            out.append(line)
            continue
        if in_doc:
            out.append(line)
            continue
        new = fix_line(line)
        if new != line:
            changed += 1
        out.append(new)
    new_src = "\n".join(out)
    open(PATH, "w", encoding="utf-8").write(new_src)
    print("修改行数:", changed)
    try:
        compile(new_src, PATH, "exec")
        print("语法检查通过")
        return 0
    except SyntaxError as e:
        ls = new_src.split("\n")
        print("语法错误:", e.lineno, e.msg)
        for i in range(max(0, e.lineno - 3), min(len(ls), e.lineno + 2)):
            print(i + 1, repr(ls[i])[:240])
        return 1


if __name__ == "__main__":
    sys.exit(main())

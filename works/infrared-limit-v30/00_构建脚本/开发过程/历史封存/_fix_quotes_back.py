# -*- coding: utf-8 -*-
"""把被误替换成中文引号、但实际是 Python 定界符的 “/” 改回 ASCII 双引号。

判据：中文引号的前/后邻字符若是 ASCII（空白、括号、逗号、字母等），说明它处在代码上下文，
应还原为 Python 字符串定界符；若邻字符是汉字或中文/全角标点，则保留为中文引号。
"""
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"


def cjkish(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF) or (0x3000 <= o <= 0x303F) or (0xFF00 <= o <= 0xFFEF) \
        or (0x2000 <= o <= 0x206F)


def fix_line(line: str) -> str:
    out = []
    n = len(line)
    for i, ch in enumerate(line):
        if ch in "“”":
            prev = line[i - 1] if i > 0 else ""
            nxt = line[i + 1] if i + 1 < n else ""
            if ch == "“" and not cjkish(prev):
                out.append('"')
                continue
            if ch == "”" and not cjkish(nxt):
                out.append('"')
                continue
        out.append(ch)
    return "".join(out)


def main():
    src = open(PATH, encoding="utf-8").read()
    lines = src.split("\n")
    out, changed = [], 0
    in_doc = False
    for line in lines:
        if line.count('"""') % 2 == 1:
            in_doc = not in_doc
            out.append(line)
            continue
        if in_doc:
            out.append(line)
            continue
        new = fix_line(line)
        changed += new != line
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

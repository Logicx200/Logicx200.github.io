# -*- coding: utf-8 -*-
"""report.py 逐轮收敛修补（v2）：编译失败时按位置做通用修复。"""
import re
import sys

PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"


def auto_fix_line(line: str) -> str:
    # 1) 中文左引号“ 出现在 ) ] } , 之前 → 应为 Python 定界符
    line = re.sub(r'“(?=[)\]},])', '"', line)
    # 2) 中文右引号” 出现在 ) ] } , 之前 → 应为 Python 定界符
    line = re.sub(r'”(?=[)\]},])', '"', line)
    # 3) 中文引号出现在行尾 → 收尾定界符
    line = re.sub(r'[“”]$', '"', line)
    # 4) 中文左引号紧跟 ASCII 字母/数字 → 定界符
    line = re.sub(r'“(?=[A-Za-z0-9_])', '"', line)
    return line


def try_compile(src):
    try:
        compile(src, PATH, "exec")
        return None
    except SyntaxError as e:
        return e


src = open(PATH, encoding="utf-8").read()
ok = False
for _ in range(30):
    e = try_compile(src)
    if e is None:
        print("语法检查通过")
        ok = True
        break
    ls = src.split("\n")
    print("语法错误:", e.lineno, e.msg, "|", repr(ls[e.lineno - 1])[:200])
    lines = src.split("\n")
    idx = e.lineno - 1
    fixed = auto_fix_line(lines[idx])
    # 同一声明块里向前后各修一行，加快收敛
    for j in (idx - 1, idx + 1):
        if 0 <= j < len(lines):
            fj = auto_fix_line(lines[j])
            if fj != lines[j]:
                lines[j] = fj
    if fixed == lines[idx]:
        # 尝试整片上下文
        changed = False
        for j in range(max(0, idx - 3), min(len(lines), idx + 3)):
            fj = auto_fix_line(lines[j])
            if fj != lines[j]:
                lines[j] = fj
                changed = True
        if not changed:
            print("无自动规则可用，请人工处理 L%d" % (idx + 1))
            break
    else:
        lines[idx] = fixed
    src = "\n".join(lines)
open(PATH, "w", encoding="utf-8").write(src)
sys.exit(0 if ok else 1)

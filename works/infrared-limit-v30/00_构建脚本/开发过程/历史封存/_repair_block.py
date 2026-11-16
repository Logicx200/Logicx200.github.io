# -*- coding: utf-8 -*-
"""修复上一步插入时产生的字面量 \\n 与缩进问题。"""
PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
s = open(PATH, encoding="utf-8").read()
lines = s.split("\n")

i_start = next(i for i, l in enumerate(lines) if 'heading(doc, "3.3  两类机制' in l)
i_end = next(i for i, l in enumerate(lines) if 'heading(doc, "3.4  真实气候工况' in l)

block = [
    '    heading(doc, "3.3  两类机制：分辨率锁死与大气折减", 2)',
    '    body(doc, "把 η 作为纵轴、目标特征尺寸作为横轴，可以清楚看到两条机制的交接：D_eff 小于约 20 m 时 η≈1，"',
    '              "识别距离完全由“传感器采样 + 目标角尺寸”决定，大气工况只在极端条件下才起作用；"',
    '              "D_eff 超过约 50 m 后 η 快速下降到 0.35–0.46，此时 R_res 已远超大气能支撑的距离，"',
    '              "识别极限改由气溶胶/水汽/湍流决定。这一交接点不是常数，随 AOD、Cn²、平台高度移动。"）'.replace("）", ")"),
    '    figure(doc, os.path.join(fig_dir, "图17_识别极限包络.png"), 14.5,',
    '           "图 13  识别极限包络：分辨率天花板 vs 实际临界距离")',
    '    figure(doc, os.path.join(fig_dir, "图13_相图_AODxCn2.png"), 16.0,',
    '           "图 14  临界状态相图：AOD₅₅₀ × Cn² 对 F16（左）与尼米兹航母（右）识别距离的联合作用")',
    '    figure(doc, os.path.join(fig_dir, "图14_相图_温差xAOD.png"), 13.6,',
    '           "图 15  临界状态相图：固有温差 × AOD₅₅₀（F16，等值线为 R₅₀）")',
    '',
]
new_lines = lines[:i_start] + block + lines[i_end:]
s2 = "\n".join(new_lines)
open(PATH, "w", encoding="utf-8").write(s2)
try:
    compile(s2, PATH, "exec")
    print("syntax OK")
except SyntaxError as e:
    ls = s2.split("\n")
    print("ERR", e.lineno, e.msg)
    for i in range(max(0, e.lineno - 3), min(len(ls), e.lineno + 2)):
        print(i + 1, repr(ls[i])[:200])

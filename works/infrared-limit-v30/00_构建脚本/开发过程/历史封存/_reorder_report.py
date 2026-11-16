# -*- coding: utf-8 -*-
"""report.py 章节与图号重排：使图号按出现顺序递增 5,6 | 7-12 | 13,14,15 | 16 | 17。"""
PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
s = open(PATH, encoding="utf-8").read()

# 1) 单变量各小节编号 3.3.x -> 3.2.x
for i in range(1, 7):
    s = s.replace(f'"3.3.{i}  ', f'"3.2.{i}  ')

# 2) 在“3.4 真实气候工况”之前插入“3.3 两类机制”整块（含图 13/14/15）
insert = (
    '    heading(doc, "3.3  两类机制：分辨率锁死与大气折减", 2)\n'
    '    body(doc, "把 η 作为纵轴、目标特征尺寸作为横轴，可以清楚看到两条机制的交接：D_eff 小于约 20 m 时 η≈1，"\\n'
    '              "识别距离完全由“传感器采样 + 目标角尺寸”决定，大气工况只在极端条件下才起作用；"\\n'
    '              "D_eff 超过约 50 m 后 η 快速下降到 0.35–0.46，此时 R_res 已远超大气能支撑的距离，"\\n'
    '              "识别极限改由气溶胶/水汽/湍流决定。这一交接点不是常数，随 AOD、Cn²、平台高度移动。")\n'
    '    figure(doc, os.path.join(fig_dir, "图17_识别极限包络.png"), 14.5,\n'
    '           "图 13  识别极限包络：分辨率天花板 vs 实际临界距离")\n'
    '    figure(doc, os.path.join(fig_dir, "图13_相图_AODxCn2.png"), 16.0,\n'
    '           "图 14  临界状态相图：AOD₅₅₀ × Cn² 对 F16（左）与尼米兹航母（右）识别距离的联合作用")\n'
    '    figure(doc, os.path.join(fig_dir, "图14_相图_温差xAOD.png"), 13.6,\n'
    '           "图 15  临界状态相图：固有温差 × AOD₅₅₀（F16，等值线为 R₅₀）")\n\n'
    '    heading(doc, "3.4  真实气候工况", 2)'
)
old_heading = 'heading(doc, "3.4  真实气候工况", 2)'
assert old_heading in s
s = s.replace(old_heading, insert, 1)

# 3) 真实气候与敏感性图的编号顺移
s = s.replace('"图 15  8 类真实环境', '"图 16  8 类真实环境')
s = s.replace('"图 16  单变量对 R₅₀', '"图 17  单变量对 R₅₀')

# 4) 第 4 章删除重复的相图插入块（已移到 3.3）
old_block_start = '    heading(doc, "4.2  临界状态相图", 2)'
if old_block_start in s:
    a = s.index(old_block_start)
    b = s.index('    heading(doc, "4.3  热交叉识别盲区（临界温差）", 2)')
    s = s[:a] + s[b:]

open(PATH, "w", encoding="utf-8").write(s)
try:
    compile(s, PATH, "exec")
    print("syntax OK")
except SyntaxError as e:
    ls = s.split("\n")
    print("ERR", e.lineno, e.msg)
    for i in range(max(0, e.lineno - 2), min(len(ls), e.lineno + 1)):
        print(i + 1, repr(ls[i])[:200])

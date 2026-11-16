# -*- coding: utf-8 -*-
"""调整方法章图序：图 1 放 1.2 节末，图 2 先于图 3。"""
PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
s = open(PATH, encoding="utf-8").read()

FIG1 = ('    figure(doc, os.path.join(fig_dir, "图01_模型链路与三类极限.png"), 16.0,\n'
        '           "图 1  识别概率极限的评估链路与三类边界")\n')
FIG3 = ('    figure(doc, os.path.join(fig_dir, "图03_光谱大气透过率.png"), 15.6,\n'
        '           "图 3  不同气候工况下的 MWIR/LWIR 光谱透过率与波段平均透过率")\n')
FIG2 = ('    figure(doc, os.path.join(fig_dir, "图02_工况空间与默认工况定位.png"), 13.2,\n'
        '           "图 2  真实气候工况空间（NASA POWER/MERRA-2 2015–2024）与软件默认工况定位")\n')
BODY = ('    body(doc, "数值收敛性已单独校核：波数步长 0.2 cm⁻¹ 相对 0.05 cm⁻¹ 的 τ_band 误差 <0.05%（1.0 cm⁻¹ 为 −2.4%）；"\n'
        '              "分层数 20 层相对 40/80/160 层误差 <0.05%。基线工况下 MWIR 波段平均透过率 1/10/20 km 约 0.71/0.67/0.62。")\n')

for x in (FIG1, FIG3, FIG2, BODY):
    assert x in s, x[:40]

# 1) 图 1 移到 1.2 节末尾
s = s.replace(FIG1, "", 1)
anchor13 = '    heading(doc, "1.3  与 V2.1 的关系（本次重构做了什么）", 2)'
assert anchor13 in s
s = s.replace(anchor13, FIG1 + "\n" + anchor13, 1)

# 2) 图 2 放到图 3 之前
old = FIG3 + BODY + FIG2
new = FIG2 + FIG3 + BODY
assert old in s
s = s.replace(old, new, 1)

open(PATH, "w", encoding="utf-8").write(s)
compile(s, PATH, "exec")
print("ok")

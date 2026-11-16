# -*- coding: utf-8 -*-
"""修正报告中对 LWIR 光谱组分的描述（含 CO2，不含 O3）。"""
PATH = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\04_模型代码\irrecog\report.py"
s = open(PATH, encoding="utf-8").read()

old1 = "气体吸收使用 HITRAN2020 逐线 Voigt 截面（H₂O、CO₂、CH₄，LWIR 另含 O₃），温度按 250/280/300 K 三节点插值。"
new1 = ("气体吸收使用 HITRAN2020 逐线 Voigt 截面（MWIR：H₂O/CO₂/CH₄；LWIR：H₂O/CO₂），"
        "温度按 250/280/300 K 三节点插值。")
assert old1 in s
s = s.replace(old1, new1)

old2 = "LWIR 目前只含 H₂O 吸收截面，O₃ 9.6 μm 带补齐后 LWIR 的 τ 会略降。"
new2 = ("LWIR 当前含 H₂O 与 CO₂ 截面，未含 O₃ 9.6 μm 带与 CH₄/N₂O 弱带；"
        "按光谱大气校验报告的估计，O₃ 会使 LWIR 波段透过率下降约 1–3 个百分点。")
assert old2 in s
s = s.replace(old2, new2)

open(PATH, "w", encoding="utf-8").write(s)
compile(s, PATH, "exec")
print("ok")

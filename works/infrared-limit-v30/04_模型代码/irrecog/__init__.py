# -*- coding: utf-8 -*-
"""
irrecog —— 红外目标识别概率极限与临界状态仿真

模块
----
params        参数唯一真值源（含依据分类 SYS/LIT/DER/SET）
radiometry    普朗克辐射、波段加权、视在温度反演
atmosphere    光谱大气：HITRAN 吸收截面 + 气溶胶 + 分子散射 + 斜程分层 + 路径辐射
sensor        传感器光学链、MTF、MRTD、f_max
target        软件模型库 6 个实际目标
probability   TTPF 任务概率与两套 N50 判据
chain         单点正向评估
critical      临界状态反解（临界距离/温差/气溶胶/湍流/口径/判据）
experiments   单变量 OFAT 实验矩阵
plots         图件
plots_atmo    光谱大气图件
"""

from . import params, radiometry, sensor, target, probability, atmosphere  # noqa: F401
from . import chain, critical  # noqa: F401

__all__ = ["params", "radiometry", "sensor", "target", "probability",
           "atmosphere", "chain", "critical"]

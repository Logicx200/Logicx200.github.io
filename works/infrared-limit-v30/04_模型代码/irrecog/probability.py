# -*- coding: utf-8 -*-
"""
irrecog.probability —— 任务概率（TTPF）与判据口径

模型
----
    N = f_max · θ_target        （目标上的周期数，θ 单位 mrad，f 单位 cycles/mrad）
    P(N) = (N/N50)^E / (1 + (N/N50)^E)

来源：Vollmerhausen & Jacobs, *The Targeting Task Performance (TTP) Metric*,
NVESD 2004（DOI:10.21236/ADA422493）；E=2 为标准 TTPF 形状参数。

两套 N50 口径（**必须绑定来源，禁止混用**）
------------------------------------------
* ``NVESD``  ：探测 4.0 / 识别 16.5 / 辨认 26.6（cycles across target，主口径）
* ``JOHNSON``：探测 2.0 / 识别 8.0 / 辨认 16.0（line pairs，经典 Johnson 口径，作敏感性对照）

说明：N 是"目标上跨越的周期数"，与 line pair 在条形靶意义下等价，
因此两套口径数值上的差异反映的是标定体系差异（约 2 倍），
本项目在报告中同时给出，而**不擅自合并**。
"""

from typing import Dict

import numpy as np

from . import params

TASK_KEYS = ("detect", "recognize", "identify")
TASK_CN = {"detect": "探测", "recognize": "识别", "identify": "辨认"}


def n50_set(name: str) -> Dict[str, float]:
    if name not in params.N50_SETS:
        raise KeyError(f"未知 N50 口径: {name}")
    return params.N50_SETS[name]


def p_task(n_cycles, n50: float, exponent: float = None) -> np.ndarray:
    """TTPF 任务概率；N≤0 时概率为 0。"""
    e = params.CRITERIA["ttpf_exponent"] if exponent is None else exponent
    n = np.maximum(np.asarray(n_cycles, dtype=float), 0.0)
    r = np.power(n / max(float(n50), 1e-12), e)
    return r / (1.0 + r)


def n_for_probability(p: float, n50: float, exponent: float = None) -> float:
    """反解达到给定概率所需的周期数（用于临界状态解析解）。"""
    e = params.CRITERIA["ttpf_exponent"] if exponent is None else exponent
    p = float(np.clip(p, 1e-9, 1 - 1e-9))
    return float(n50 * (p / (1.0 - p)) ** (1.0 / e))


def p_curve(n_cycles, n50: float, exponent: float = None) -> np.ndarray:
    return p_task(n_cycles, n50, exponent)

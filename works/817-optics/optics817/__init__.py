# -*- coding: utf-8 -*-
"""optics817 —— 面向考研 817《光学》的最小可用仿真库。

模块与考纲的对应关系（国科大 817 大纲，物理光学 60% + 应用光学 40%）：

    wave            第一章 光的电磁理论基础（菲涅耳公式、全反射、琼斯矩阵）
    interference    第二章 光的干涉（双光束、多光束、薄膜、干涉仪）
    diffraction     第三章 光的衍射（夫琅禾费、菲涅耳、光栅、波带片）
    fourier_optics  第三章第五节 傅里叶光学 + 通用光场传播
    polarization    第四章/第五章 各向异性介质、双折射、波片、电光声光
    geometrical     第七章/第八章/第九章 几何光学、理想系统、光阑像差
    instruments     第十章 光学仪器（眼睛、放大镜、显微镜、望远镜）

约定：
    * 长度单位一律用米（m），波长用 m；若用 nm 请自行乘 1e-9。
    * 角度：函数参数一般为弧度；变量名带 _deg 的才是度。
    * 强度量默认归一化到 I0 = 1。
"""
from __future__ import annotations

__version__ = "1.0.0"

from . import plotstyle  # noqa: F401  （先导入，保证中文字体设置生效）
from . import wave  # noqa: F401
from . import interference  # noqa: F401
from . import fourier_optics  # noqa: F401
from . import diffraction  # noqa: F401
from . import polarization  # noqa: F401
from . import geometrical  # noqa: F401
from . import instruments  # noqa: F401

__all__ = [
    "wave",
    "interference",
    "diffraction",
    "fourier_optics",
    "polarization",
    "geometrical",
    "instruments",
    "plotstyle",
]

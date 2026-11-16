# -*- coding: utf-8 -*-
"""绘图工具: 中文字体自动配置 + 统一风格."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


_CJK_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC",
    "Source Han Sans CN", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
    "PingFang SC", "Hiragino Sans GB", "SimSun", "Arial Unicode MS",
]


def setup_style():
    """配置中文字体与统一绘图风格; 返回是否成功找到中文字体."""
    have = False
    try:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        for name in _CJK_CANDIDATES:
            if name in installed:
                plt.rcParams["font.sans-serif"] = [name] + plt.rcParams["font.sans-serif"]
                have = True
                break
    except Exception:
        pass
    plt.rcParams.update({
        "axes.unicode_minus": False,
        "figure.dpi": 130,
        "savefig.dpi": 130,
        "font.size": 10.5,
        "axes.titlesize": 11.5,
        "axes.labelsize": 10.5,
        "legend.fontsize": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": ":",
        "axes.axisbelow": True,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
    })
    return have


def marker(i):
    return ["o", "s", "^", "v", "D", "P", "X", "*"][i % 8]


def color(i):
    return plt.get_cmap("tab10")(i % 10)

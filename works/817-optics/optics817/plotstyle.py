# -*- coding: utf-8 -*-
"""绘图统一样式：解决 matplotlib 中文显示为方框的问题。

用法：
    from optics817.plotstyle import use_chinese_font, save_fig
    use_chinese_font()
"""
from __future__ import annotations

import os

import matplotlib

# 常见中文字体（按优先级）。Windows 一般有 Microsoft YaHei / SimHei。
CJK_FONTS = (
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "PingFang SC",
    "Heiti SC",
    "Arial Unicode MS",
)

OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def use_chinese_font(verbose: bool = False) -> str | None:
    """把可用的中文字体挂到 rcParams 前面，返回实际选中的字体名。"""
    from matplotlib import font_manager, rcParams

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = None
    for name in CJK_FONTS:
        if name in available:
            chosen = name
            break
    if chosen:
        rcParams["font.sans-serif"] = [chosen] + list(rcParams["font.sans-serif"])
    rcParams["axes.unicode_minus"] = False  # 负号正常显示
    rcParams["figure.dpi"] = 110
    rcParams["savefig.dpi"] = 140
    rcParams["axes.grid"] = True
    rcParams["grid.alpha"] = 0.25
    if verbose:
        print(f"[plotstyle] 使用中文字体: {chosen or '未找到，图中中文可能显示为方框'}")
    return chosen


def save_fig(fig, name: str, outdir: str | None = None) -> str:
    """保存图片到 outputs/ 并返回完整路径。"""
    outdir = outdir or OUTDIR
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name)
    try:
        fig.tight_layout()
    except Exception:
        pass  # 版式不完美也要保证出图
    fig.savefig(path, bbox_inches="tight")
    print(f"[fig] 已保存 -> {path}")
    return path


# 导入即生效，demo 里不用再写一遍
use_chinese_font()

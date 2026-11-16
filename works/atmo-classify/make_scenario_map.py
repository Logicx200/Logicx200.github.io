# -*- coding: utf-8 -*-
"""
红外目标探测大气工况分类图
====================================================================
二维平面 : 横轴 sigma_a(550) [km^-1, 对数]  x  纵轴 PWV [cm]
第三维   : Angstrom 消光指数 alpha（颜色编码：蓝=粗模态, 红=细模态）
====================================================================
输出 : 工况分类图.png / .svg / .pdf
"""

import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import (
    LinearSegmentedColormap,
    Normalize,
    to_rgb,
    to_rgba,
    rgb_to_hsv,
    hsv_to_rgb,
)
from matplotlib.cm import ScalarMappable
from matplotlib.ticker import FixedLocator, NullFormatter

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 全局风格
plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DengXian", "Arial"],
        "axes.unicode_minus": False,
        "mathtext.fontset": "dejavusans",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.edgecolor": "#9a9a9a",
        "axes.linewidth": 0.9,
    }
)

# alpha 色标：深蓝(粗模态) -> 浅蓝 -> 奶黄 -> 橙 -> 深红(细模态)
ALPHA_MIN, ALPHA_MAX = -0.2, 1.8
CMAP = LinearSegmentedColormap.from_list(
    "alpha_mode",
    [
        (0.00, "#313695"),
        (0.18, "#4575B4"),
        (0.34, "#74ADD1"),
        (0.46, "#ABD9E9"),
        (0.54, "#FFFFBF"),
        (0.62, "#FEE090"),
        (0.74, "#FDAE61"),
        (0.88, "#F46D43"),
        (1.00, "#A50026"),
    ],
)
NORM = Normalize(vmin=ALPHA_MIN, vmax=ALPHA_MAX)


def strong_edge(color, sat=1.75, val=0.70):
    """把淡色边强调成同色系深色，保证虚线框清晰可辨。"""
    h, s, _v = rgb_to_hsv(np.asarray(to_rgb(color)))
    s = min(1.0, s * sat + 0.10)
    if 0.10 < h < 0.25:  # 奶黄/浅金：避免加深后变成橄榄绿，锁定为金色系
        h = 0.115
        s = max(s, 0.55)
    return tuple(hsv_to_rgb((h, s, val)))


# ---------------------------------------------------------------- 工况数据
# (编号, 名称, sigma_a 范围, PWV 范围, alpha 范围, 标签位置, alpha 定性描述)
SCENARIOS = [
    dict(
        tag="①",
        name="沙漠背景 / 浮尘",
        x0=0.05, x1=0.50, y0=0.5, y1=2.5,
        a0=0.2, a1=0.5,
        label_xy=(0.25, 1.00),
        mode="粗模态",
    ),
    dict(
        tag="②",
        name="沙漠沙尘事件",
        x0=0.90, x1=2.00, y0=0.5, y1=2.5,
        a0=-0.1, a1=0.2,
        label_xy=(1.42, 1.05),
        mode="近中性",
    ),
    dict(
        tag="③",
        name="乡村清洁",
        x0=0.02, x1=0.15, y0=1.0, y1=2.5,
        a0=0.5, a1=1.2,
        label_xy=(0.055, 1.85),
        mode="混合 / 偏细",
    ),
    dict(
        tag="④",
        name="乡村农业 / 燃烧",
        x0=0.20, x1=0.70, y0=1.5, y1=4.0,
        a0=0.5, a1=1.5,
        label_xy=(0.26, 2.15),
        mode="混合",
    ),
    dict(
        tag="⑤",
        name="海岛 / 海洋清洁",
        x0=0.03, x1=0.15, y0=2.0, y1=5.0,
        a0=0.0, a1=1.0,
        label_xy=(0.064, 3.10),
        mode="海洋粗模态为主",
    ),
    dict(
        tag="⑥",
        name="海岛 / 近岸污染",
        x0=0.20, x1=0.80, y0=2.5, y1=6.0,
        a0=0.5, a1=1.5,
        label_xy=(0.25, 4.85),
        mode="混合 / 偏细",
    ),
    dict(
        tag="⑦",
        name="城市 / 工业",
        x0=0.30, x1=1.50, y0=1.5, y1=4.5,
        a0=1.0, a1=1.8,
        label_xy=(0.92, 3.92),
        mode="细模态",
    ),
]

for s in SCENARIOS:
    s["amid"] = 0.5 * (s["a0"] + s["a1"])
    s["color"] = CMAP(NORM(s["amid"]))
    s["edge"] = strong_edge(s["color"])


def fmt_a(v):
    """alpha 数值：负数用真减号，正数不带 '+'。"""
    return ("−" + f"{abs(v):.1f}") if v < 0 else f"{v:.1f}"


# ---------------------------------------------------------------- 画布
FIG_W, FIG_H = 12.8, 9.0
fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=120)
ax = fig.add_axes([0.070, 0.190, 0.875, 0.665])
ax.set_facecolor("white")

X_MIN, X_MAX = 0.018, 2.75
Y_MIN, Y_MAX = 0.0, 6.6
ax.set_xscale("log")
ax.set_xlim(X_MIN, X_MAX)
ax.set_ylim(Y_MIN, Y_MAX)

# ---------------------------------------------------------------- 网格
ax.set_axisbelow(True)
ax.grid(which="major", axis="both", color="#d7d7d7", lw=0.75)
ax.grid(which="minor", axis="x", color="#ececec", lw=0.5)

# ---------------------------------------------------------------- 数据框
ORDER = ["⑤", "⑥", "⑦", "④", "①", "③", "②"]  # 先画大框, 后画小框
by_tag = {s["tag"]: s for s in SCENARIOS}
for tag in ORDER:
    s = by_tag[tag]
    rect = Rectangle(
        (s["x0"], s["y0"]),
        s["x1"] - s["x0"],
        s["y1"] - s["y0"],
        facecolor=to_rgba(s["color"], 0.17),
        edgecolor=s["edge"],
        linewidth=2.0,
        linestyle=(0, (5, 2.5)),
        joinstyle="round",
        zorder=2,
    )
    ax.add_patch(rect)

# ---------------------------------------------------------------- 标签
for s in SCENARIOS:
    line1 = f"{s['tag']} {s['name']}"
    line2 = r"$\sigma_a$ " + f"{s['x0']:.2f}–{s['x1']:.2f} km$^{{-1}}$"
    if s["tag"] == "②":
        line2 = r"$\sigma_a$ 0.9–2.0+ km$^{-1}$"
    line3 = r"$\alpha$ " + f"{fmt_a(s['a0'])}–{fmt_a(s['a1'])}（{s['mode']}）"
    ax.text(
        s["label_xy"][0],
        s["label_xy"][1],
        line1 + "\n" + line2 + "\n" + line3,
        ha="center",
        va="center",
        fontsize=7.9,
        linespacing=1.42,
        color="#1f1f1f",
        zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.34",
            facecolor=(1, 1, 1, 0.93),
            edgecolor=s["edge"],
            linewidth=1.1,
            alpha=1.0,
        ),
    )

# ---------------------------------------------------------------- 沙尘事件向右延伸箭头
ax.annotate(
    "",
    xy=(2.55, 1.5),
    xytext=(2.04, 1.5),
    arrowprops=dict(
        arrowstyle="-|>",
        color="#7a7a7a",
        lw=1.3,
        linestyle=(0, (4, 2)),
        mutation_scale=13,
        shrinkA=0,
        shrinkB=0,
    ),
    zorder=5,
)
ax.text(
    2.30, 1.62, "消光更强", fontsize=7.2, color="#6b6b6b", ha="center", va="bottom"
)

# ---------------------------------------------------------------- 坐标轴
ax.set_xlabel(
    r"550 nm 气溶胶消光系数  $\sigma_a(550)$（km$^{-1}$，对数坐标）",
    fontsize=11,
    labelpad=9,
)
ax.set_ylabel(r"可降水量  PWV（cm）", fontsize=11, labelpad=8)

ax.xaxis.set_major_locator(FixedLocator([0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]))
ax.set_xticklabels(["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"], fontsize=10)
ax.xaxis.set_minor_formatter(NullFormatter())
ax.set_yticks(np.arange(0, 7, 1))
ax.tick_params(axis="both", which="major", labelsize=10, length=4, width=0.9)
ax.tick_params(axis="x", which="minor", length=2.4, width=0.7, color="#9a9a9a")

# ---------------------------------------------------------------- 色标（内嵌右上空白区，横排）
sm = ScalarMappable(norm=NORM, cmap=CMAP)
cax = ax.inset_axes([0.780, 0.798, 0.192, 0.028])
cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
cb.set_ticks([0.0, 0.5, 1.0, 1.5])
cb.ax.tick_params(labelsize=7.6, length=2.6, width=0.7, pad=2)
cb.outline.set_edgecolor("#8a8a8a")
cb.outline.set_linewidth(0.6)
ax.text(
    0.780,
    0.878,
    r"第三维：Ångström 波长指数  $\alpha$",
    transform=ax.transAxes,
    fontsize=8.8,
    color="#222222",
    ha="left",
    va="center",
)
ax.text(
    0.780,
    0.851,
    "消光光谱斜率（非消光强度）",
    transform=ax.transAxes,
    fontsize=7.4,
    color="#6b6b6b",
    ha="left",
    va="center",
)

# ---------------------------------------------------------------- 标题
fig.text(
    0.5,
    0.966,
    "红外目标探测大气工况分类图：气溶胶消光 × 水汽二维平面",
    ha="center",
    va="center",
    fontsize=17.5,
    fontweight="bold",
    color="#111111",
)
fig.text(
    0.5,
    0.927,
    r"横轴：550 nm 气溶胶消光系数 $\sigma_a(550)$ ｜ 纵轴：可降水量 PWV ｜ 颜色编码：Ångström 波长指数 $\alpha$（消光光谱斜率；蓝 → 粗模态，红 → 细模态）",
    ha="center",
    va="center",
    fontsize=10.2,
    color="#444444",
)
fig.text(
    0.5,
    0.891,
    "虚线框为该工况的近似范围（非硬边界）：框的横向范围即 σa 区间，纵向范围即 PWV 区间",
    ha="center",
    va="center",
    fontsize=8.9,
    color="#6a6a6a",
)

# ---------------------------------------------------------------- 脚注
notes = [
    "注：① 范围据典型观测 / 文献经验值整理，仅为近似框定；半透明重叠区为两块范围叠加，不代表新的工况；城市 / 工业在二维平面上与乡村污染端、沙尘高消光端显著重叠，需结合 α、H_a 与单次散射反照率进一步判别。",
    r"② $\sigma_a(550)\approx\mathrm{AOD}/H_a$（H_a ≈ 1 km 时数值近似 AOD）；PWV 与 $\sigma_a$ 并非独立（高湿吸湿增长使细模态端呈正相关）；$\alpha$ 仅适用于气溶胶消光外推，不能用于水汽吸收，PWV 需配合温湿廓线逐层计算 $k_{\mathrm{H_2O}}$。",
    "③ 实际应用时建议以目标区域 PWV 气候态和当地气溶胶类型替换上述通用范围；等效红外能见度需另行声明对比度阈值（建议 5%）与路径类型。",
]
fig.text(
    0.070,
    0.078,
    "\n".join(notes),
    ha="left",
    va="top",
    fontsize=8.0,
    linespacing=1.65,
    color="#3d3d3d",
)

# ---------------------------------------------------------------- 保存
png_path = os.path.join(HERE, "工况分类图.png")
svg_path = os.path.join(HERE, "工况分类图.svg")
pdf_path = os.path.join(HERE, "工况分类图.pdf")
fig.savefig(png_path, dpi=300)
fig.savefig(svg_path)
fig.savefig(pdf_path)
print("saved:", png_path)
print("saved:", svg_path)
print("saved:", pdf_path)

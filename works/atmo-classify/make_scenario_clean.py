# -*- coding: utf-8 -*-
"""
红外目标探测大气工况分类图（无插值版）
====================================================================
二维平面 : 横轴 sigma_a(550) [km^-1, 对数]  x  纵轴 PWV [cm]
框线颜色 : Angstrom 消光指数 alpha 的典型值（不填色、不做空间插值）
====================================================================
输出 : 工况分类图_无插值.png / .svg / .pdf
"""

import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgb, rgb_to_hsv, hsv_to_rgb
from matplotlib.cm import ScalarMappable
from matplotlib.ticker import FixedLocator, NullFormatter

HERE = os.path.dirname(os.path.abspath(__file__))

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

ALPHA_MIN, ALPHA_MAX = -0.2, 1.8
CMAP = LinearSegmentedColormap.from_list(
    "alpha_mode",
    [
        (0.00, "#22307A"),
        (0.16, "#3465B0"),
        (0.32, "#6AAED6"),
        (0.45, "#B7DCEB"),
        (0.53, "#F5E6A3"),
        (0.61, "#F7C85B"),
        (0.73, "#EF8A3C"),
        (0.87, "#D94F2B"),
        (1.00, "#9E1B23"),
    ],
)
NORM = Normalize(vmin=ALPHA_MIN, vmax=ALPHA_MAX)


def strong_edge(color, sat=1.75, val=0.70):
    h, s, _v = rgb_to_hsv(np.asarray(to_rgb(color)))
    s = min(1.0, s * sat + 0.10)
    if 0.10 < h < 0.25:
        h = 0.115
        s = max(s, 0.55)
    return tuple(hsv_to_rgb((h, s, val)))


SCENARIOS = [
    dict(tag="①", name="沙漠背景 / 浮尘", x0=0.05, x1=0.50, y0=0.5, y1=2.5,
         a0=0.2, a1=0.5, label_xy=(0.25, 1.00), mode="粗模态"),
    dict(tag="②", name="沙漠沙尘事件", x0=0.90, x1=2.00, y0=0.5, y1=2.5,
         a0=-0.1, a1=0.2, label_xy=(1.42, 1.05), mode="近中性"),
    dict(tag="③", name="乡村清洁", x0=0.02, x1=0.15, y0=1.0, y1=2.5,
         a0=0.5, a1=1.2, label_xy=(0.055, 1.85), mode="混合 / 偏细"),
    dict(tag="④", name="乡村农业 / 燃烧", x0=0.20, x1=0.70, y0=1.5, y1=4.0,
         a0=0.5, a1=1.5, label_xy=(0.26, 2.15), mode="混合"),
    dict(tag="⑤", name="海岛 / 海洋清洁", x0=0.03, x1=0.15, y0=2.0, y1=5.0,
         a0=0.0, a1=1.0, label_xy=(0.064, 3.10), mode="海洋粗模态为主"),
    dict(tag="⑥", name="海岛 / 近岸污染", x0=0.20, x1=0.80, y0=2.5, y1=6.0,
         a0=0.5, a1=1.5, label_xy=(0.25, 4.85), mode="混合 / 偏细"),
    dict(tag="⑦", name="城市 / 工业", x0=0.30, x1=1.50, y0=1.5, y1=4.5,
         a0=1.0, a1=1.8, label_xy=(0.92, 3.92), mode="细模态"),
]
for s in SCENARIOS:
    s["amid"] = 0.5 * (s["a0"] + s["a1"])
    s["color"] = CMAP(NORM(s["amid"]))
    s["edge"] = strong_edge(s["color"])


def fmt_a(v):
    return ("−" + f"{abs(v):.1f}") if v < 0 else f"{v:.1f}"


FIG_W, FIG_H = 12.8, 9.0
fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=120)
ax = fig.add_axes([0.070, 0.190, 0.820, 0.665])

X_MIN, X_MAX = 0.018, 2.75
Y_MIN, Y_MAX = 0.0, 6.6
ax.set_xscale("log")
ax.set_xlim(X_MIN, X_MAX)
ax.set_ylim(Y_MIN, Y_MAX)
ax.set_axisbelow(True)
ax.grid(which="major", axis="both", color="#dcdcdc", lw=0.8)
ax.grid(which="minor", axis="x", color="#efefef", lw=0.5)

# 工况范围框：仅虚线轮廓，框线颜色 = 该工况典型 alpha
for s in SCENARIOS:
    rect = Rectangle(
        (s["x0"], s["y0"]),
        s["x1"] - s["x0"],
        s["y1"] - s["y0"],
        facecolor="none",
        edgecolor=s["edge"],
        linewidth=2.2,
        linestyle=(0, (5, 2.4)),
        joinstyle="round",
        zorder=3,
    )
    ax.add_patch(rect)

# 标签
for s in SCENARIOS:
    line1 = f"{s['tag']} {s['name']}"
    line2 = r"$\sigma_a$ " + f"{s['x0']:.2f}–{s['x1']:.2f} km$^{{-1}}$"
    if s["tag"] == "②":
        line2 = r"$\sigma_a$ 0.9–2.0+ km$^{-1}$"
    line3 = r"$\alpha$ " + f"{fmt_a(s['a0'])}–{fmt_a(s['a1'])}（{s['mode']}）"
    ax.text(
        s["label_xy"][0], s["label_xy"][1],
        line1 + "\n" + line2 + "\n" + line3,
        ha="center", va="center", fontsize=7.9, linespacing=1.42,
        color="#1a1a1a", zorder=6,
        bbox=dict(boxstyle="round,pad=0.34", facecolor=(1, 1, 1, 0.93),
                  edgecolor="#4d4d4d", linewidth=0.9),
    )

# 沙尘事件向右延伸
ax.annotate(
    "", xy=(2.55, 1.5), xytext=(2.04, 1.5),
    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.3,
                    linestyle=(0, (4, 2)), mutation_scale=13,
                    shrinkA=0, shrinkB=0),
    zorder=4,
)
ax.text(2.30, 1.62, "消光更强", fontsize=7.2, color="#555555",
        ha="center", va="bottom", zorder=4)

ax.set_xlabel(r"550 nm 气溶胶消光系数  $\sigma_a(550)$（km$^{-1}$，对数坐标）",
              fontsize=11, labelpad=9)
ax.set_ylabel(r"可降水量  PWV（cm）", fontsize=11, labelpad=8)
ax.xaxis.set_major_locator(FixedLocator([0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0]))
ax.set_xticklabels(["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"], fontsize=10)
ax.xaxis.set_minor_formatter(NullFormatter())
ax.set_yticks(np.arange(0, 7, 1))
ax.tick_params(axis="both", which="major", labelsize=10, length=4, width=0.9)
ax.tick_params(axis="x", which="minor", length=2.4, width=0.7, color="#9a9a9a")

# 色标（框线颜色）
sm = ScalarMappable(norm=NORM, cmap=CMAP)
cax = fig.add_axes([0.907, 0.315, 0.0145, 0.345])
cb = fig.colorbar(sm, cax=cax, orientation="vertical")
cb.set_ticks([0.0, 0.5, 1.0, 1.5])
cb.ax.tick_params(labelsize=9, length=3, width=0.8)
cb.outline.set_edgecolor("#8a8a8a")
cb.outline.set_linewidth(0.7)
cb.set_label(r"Ångström 消光指数  $\alpha$（框线颜色）", fontsize=9.6, labelpad=11)
fig.text(0.9145, 0.690, "细模态\n（烟尘 / 城市）", ha="center", va="bottom",
         fontsize=7.4, color="#7a2b22", linespacing=1.45)
fig.text(0.9145, 0.298, "粗模态\n（沙尘 / 海盐）", ha="center", va="top",
         fontsize=7.4, color="#1c3a63", linespacing=1.45)

fig.text(0.5, 0.966,
         "红外目标探测大气工况分类图：气溶胶消光 × 水汽二维平面（无插值）",
         ha="center", va="center", fontsize=17.0, fontweight="bold", color="#111111")
fig.text(0.5, 0.927,
         r"横轴：550 nm 气溶胶消光系数 $\sigma_a(550)$ ｜ 纵轴：可降水量 PWV ｜ 框线颜色：Ångström 消光指数 $\alpha$（蓝 → 粗模态，红 → 细模态）",
         ha="center", va="center", fontsize=9.8, color="#444444")
fig.text(0.5, 0.892,
         "无背景插值：仅用虚线框给出各工况近似范围与之典型 α；框线颜色不对应消光强弱",
         ha="center", va="center", fontsize=8.8, color="#6a6a6a")

notes = [
    "注：① 框线颜色 = 该工况 Ångström 消光指数 α 的典型值（范围中值），仅用于区分粗 / 细模态；虚线框为近似范围，非硬边界，重叠区表示两工况范围相交。",
    r"② $\sigma_a(550)\approx\mathrm{AOD}/H_a$；PWV 与 $\sigma_a$ 并非独立（高湿吸湿增长使细模态端呈正相关）；$\alpha$ 仅适用于气溶胶消光外推，不能用于水汽吸收，PWV 需配合温湿廓线逐层计算 $k_{\mathrm{H_2O}}$。",
    "③ 实际应用时建议以目标区域 PWV 气候态与当地气溶胶类型替换上述通用范围；等效红外能见度需另行声明对比度阈值（建议 5%）与路径类型。",
]
fig.text(0.070, 0.078, "\n".join(notes), ha="left", va="top",
         fontsize=8.0, linespacing=1.65, color="#3d3d3d")

png_path = os.path.join(HERE, "工况分类图_无插值.png")
fig.savefig(png_path, dpi=300)
fig.savefig(os.path.join(HERE, "工况分类图_无插值.svg"))
fig.savefig(os.path.join(HERE, "工况分类图_无插值.pdf"))
print("saved:", png_path)

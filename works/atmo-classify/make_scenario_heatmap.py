# -*- coding: utf-8 -*-
"""
红外目标探测大气工况分类图（α 热力图版）
====================================================================
二维平面 : 横轴 sigma_a(550) [km^-1, 对数]  x  纵轴 PWV [cm]
背景颜色 : Angstrom 消光指数 alpha 的示意插值场（各工况典型值插值）
虚线框   : 各工况典型范围（仅轮廓，不填充）
====================================================================
输出 : 工况分类图_热力图.png / .svg / .pdf
"""

import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle
from matplotlib.colors import (
    LinearSegmentedColormap,
    Normalize,
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

# ---------------------------------------------------------------- 工况数据
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


def fmt_a(v):
    return ("−" + f"{abs(v):.1f}") if v < 0 else f"{v:.1f}"


# ---------------------------------------------------------------- 画布
FIG_W, FIG_H = 13.0, 9.0
fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=120)
ax = fig.add_axes([0.070, 0.190, 0.820, 0.665])

X_MIN, X_MAX = 0.018, 2.75
Y_MIN, Y_MAX = 0.0, 6.6
ax.set_xscale("log")
ax.set_xlim(X_MIN, X_MAX)
ax.set_ylim(Y_MIN, Y_MAX)

# ---------------------------------------------------------------- 背景 alpha 热力图（示意插值）
nx, ny = 820, 540
xg = np.logspace(np.log10(X_MIN), np.log10(X_MAX), nx)
yg = np.linspace(Y_MIN, Y_MAX, ny)
Xg, Yg = np.meshgrid(xg, yg)
LOGX = np.log10(Xg)

# 背景 alpha 场：框内取该工况典型 alpha（重叠区以“范围更窄、更具体”的工况优先），
# 框外按框距离高斯加权平滑过渡 —— 保证框内颜色与该工况标签的 alpha 一致。
SIGMA_LOGX, SIGMA_Y = 0.16, 0.55  # 框外过渡尺度：0.16 decade, 0.55 cm

dists, areas = [], []
for s in SCENARIOS:
    lx0, lx1 = np.log10(s["x0"]), np.log10(s["x1"])
    dx = np.maximum(np.maximum(lx0 - LOGX, LOGX - lx1), 0.0)
    dy = np.maximum(np.maximum(s["y0"] - Yg, Yg - s["y1"]), 0.0)
    dists.append(np.sqrt((dx / SIGMA_LOGX) ** 2 + (dy / SIGMA_Y) ** 2))
    areas.append((lx1 - lx0) * (s["y1"] - s["y0"]))
dists = np.array(dists)
areas = np.array(areas)
AMID = np.array([s["amid"] for s in SCENARIOS])

FIELD = np.full(Xg.shape, np.nan)
assigned = np.zeros(Xg.shape, dtype=bool)
for idx in np.argsort(areas):  # 范围越窄的工况优先级越高
    sel = (dists[idx] <= 1e-9) & (~assigned)
    FIELD[sel] = AMID[idx]
    assigned |= sel

# 框外：高斯距离加权平均
wgt = np.exp(-0.5 * dists**2)
num = np.sum(wgt * AMID[:, None, None], axis=0)
den = np.sum(wgt, axis=0)
FIELD[~assigned] = (num / np.maximum(den, 1e-9))[~assigned]

# 轻度平滑，消除框边界处的 1~2 像素硬跳变
for _ in range(4):
    FIELD = (
        FIELD
        + np.roll(FIELD, 1, axis=0)
        + np.roll(FIELD, -1, axis=0)
        + np.roll(FIELD, 1, axis=1)
        + np.roll(FIELD, -1, axis=1)
    ) / 5.0

ax.pcolormesh(
    xg, yg, FIELD, cmap=CMAP, norm=NORM, shading="auto", zorder=0, rasterized=True
)

# ---------------------------------------------------------------- 工况范围框（仅轮廓）
for s in SCENARIOS:
    rect = Rectangle(
        (s["x0"], s["y0"]),
        s["x1"] - s["x0"],
        s["y1"] - s["y0"],
        facecolor="none",
        edgecolor="#1b1b1b",
        linewidth=1.5,
        linestyle=(0, (4.5, 2.2)),
        joinstyle="round",
        zorder=4,
    )
    rect.set_path_effects(
        [pe.Stroke(linewidth=4.0, foreground="white", alpha=0.9), pe.Normal()]
    )
    ax.add_patch(rect)

# ---------------------------------------------------------------- 标签（中性白底卡片）
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
        color="#141414",
        zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.34",
            facecolor=(1, 1, 1, 0.93),
            edgecolor="#3d3d3d",
            linewidth=0.9,
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
        color="#333333",
        lw=1.3,
        linestyle=(0, (4, 2)),
        mutation_scale=13,
        shrinkA=0,
        shrinkB=0,
    ),
    zorder=5,
)
ax.text(
    2.30, 1.62, "消光更强", fontsize=7.2, color="#333333", ha="center", va="bottom",
    zorder=5,
    bbox=dict(boxstyle="round,pad=0.18", facecolor=(1, 1, 1, 0.75), edgecolor="none"),
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
ax.grid(False)

# ---------------------------------------------------------------- 色标（右竖排）
sm = ScalarMappable(norm=NORM, cmap=CMAP)
cax = fig.add_axes([0.907, 0.300, 0.0145, 0.360])
cb = fig.colorbar(sm, cax=cax, orientation="vertical")
cb.set_ticks([0.0, 0.5, 1.0, 1.5])
cb.ax.tick_params(labelsize=9, length=3, width=0.8)
cb.outline.set_edgecolor("#8a8a8a")
cb.outline.set_linewidth(0.7)
cb.set_label(
    r"Ångström 消光指数  $\alpha$（消光光谱斜率）",
    fontsize=9.3,
    labelpad=11,
)
fig.text(0.9145, 0.690, "细模态\n（烟尘 / 城市）", ha="center", va="bottom",
         fontsize=7.4, color="#7a2b22", linespacing=1.45)
fig.text(0.9145, 0.282, "粗模态\n（沙尘 / 海盐）", ha="center", va="top",
         fontsize=7.4, color="#1c3a63", linespacing=1.45)

# ---------------------------------------------------------------- 标题
fig.text(
    0.5,
    0.966,
    "红外目标探测大气工况分类图：气溶胶消光 × 水汽二维平面（α 热力图）",
    ha="center",
    va="center",
    fontsize=17.0,
    fontweight="bold",
    color="#111111",
)
fig.text(
    0.5,
    0.927,
    r"横轴：550 nm 气溶胶消光系数 $\sigma_a(550)$ ｜ 纵轴：可降水量 PWV ｜ 背景颜色：Ångström 消光指数 $\alpha$（消光光谱斜率，蓝 → 粗模态，红 → 细模态）",
    ha="center",
    va="center",
    fontsize=9.8,
    color="#444444",
)
fig.text(
    0.5,
    0.892,
    "背景 α 场为按各工况典型值插值的示意场（非实测 / 非辐射传输计算结果）；虚线框为各工况近似范围（非硬边界）",
    ha="center",
    va="center",
    fontsize=8.8,
    color="#6a6a6a",
)

# ---------------------------------------------------------------- 脚注
notes = [
    "注：① 背景颜色为 α 的示意场：框内取该工况典型 α，重叠区以范围更窄的工况优先，框外按距离加权平滑过渡；仅用于区分粗 / 细模态，不代表物理计算或观测结果；虚线框为近似范围，非硬边界。",
    r"② $\sigma_a(550)\approx\mathrm{AOD}/H_a$；PWV 与 $\sigma_a$ 并非独立（高湿吸湿增长使细模态端呈正相关）；$\alpha$ 仅适用于气溶胶消光外推，不能用于水汽吸收，PWV 需配合温湿廓线逐层计算 $k_{\mathrm{H_2O}}$。",
    "③ 实际应用时建议以目标区域 PWV 气候态与当地气溶胶类型替换上述通用范围；等效红外能见度需另行声明对比度阈值（建议 5%）与路径类型。",
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
png_path = os.path.join(HERE, "工况分类图_热力图.png")
svg_path = os.path.join(HERE, "工况分类图_热力图.svg")
pdf_path = os.path.join(HERE, "工况分类图_热力图.pdf")
fig.savefig(png_path, dpi=300)
fig.savefig(svg_path)
fig.savefig(pdf_path)
print("saved:", png_path)
print("saved:", svg_path)
print("saved:", pdf_path)

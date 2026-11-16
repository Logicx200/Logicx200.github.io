# -*- coding: utf-8 -*-
"""
make_mindmap.py —— 生成项目思维导图（图00：标准版 + 横版）

输出
----
    02_图表/图00_项目思维导图.png / .pdf          标准版（近方形，近方形版备份）
    02_图表/图00_项目思维导图_横版.png / .pdf      横版（约 1.8:1，供 A4 横向整页插入）

设计说明
--------
* 纯 matplotlib 手绘：根节点居中，左右各挂分支，每个分支下挂条目（叶子），
  曲线连接 + 分支浅色底板分组；中文使用 Microsoft YaHei，PDF 以 TrueType 子集嵌入，
  文本可检索，避免任何字体乱码。
* 节点层级 3 层（根 → 分支 → 条目），共 47 个节点；配色按主题分组，
  白底、大留白、无阴影，可直接放入正式报告。
* 内容口径与 04_模型代码、06_校验/公式校准报告.md 保持一致：
  - 对比度地板条件为 τ_opt·ΔT_app ≤ k·NETD；
  - 热交叉盲区表述为“ΔT→0 时对比度严格为零，存在由 NETD 地板决定的窄盲区”；
  - 小/大目标的 η 只作定性表述，具体数值以最终 03_数据 汇总表复核。
* 可重复运行：python 00_构建脚本/make_mindmap.py

依赖：matplotlib。
"""

import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, PathPatch
from matplotlib.path import Path

# --------------------------------------------------------------------------- #
# 路径与字体
# --------------------------------------------------------------------------- #
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "02_图表")
PNG_NAME = "图00_项目思维导图.png"
PDF_NAME = "图00_项目思维导图.pdf"
PNG_WIDE_NAME = "图00_项目思维导图_横版.png"
PDF_WIDE_NAME = "图00_项目思维导图_横版.pdf"

_FONT_CANDIDATES = ["Microsoft YaHei", "Microsoft YaHei UI", "SimHei", "DengXian", "Noto Sans CJK SC"]


def _pick_font():
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in _FONT_CANDIDATES:
        if name in installed:
            return name
    return "sans-serif"


FONT = _pick_font()

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [FONT, "DejaVu Sans"],
    "axes.unicode_minus": False,
    "pdf.fonttype": 42,          # TrueType 子集嵌入，PDF 中文字可检索
    "ps.fonttype": 42,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# --------------------------------------------------------------------------- #
# 内容定义（根 → 分支 → 条目，共 3 层、47 个节点）
# 文本只使用 Microsoft YaHei 确实包含的字符（避免上下标数字、≤、≥ 等缺字）。
# 小/大目标的 η 数值待最终 03_数据 的 S01 汇总出来后复核，本图先给定性表述。
# --------------------------------------------------------------------------- #
ROOT_TEXT = "红外目标识别\n概率极限与临界状态"

BRANCHES = [
    dict(
        title="项目问题",
        color="#1D4E89",
        leaves=[
            "能识别多远？\n给出 R50 / R90 临界距离与 P(R) 曲线",
            "极限由什么决定？\n分辨率天花板 / 对比度地板 / 湍流边界 三类竞争",
            "临界状态是什么？\n等性能切片：反解临界 AOD、Cn²、口径、NETD 与温差盲区",
        ],
    ),
    dict(
        title="输入与数据",
        color="#0F766E",
        leaves=[
            "XGGDCOSSim2 软件实测 6 个目标包围盒\nF16 / F22 / 尼米兹 / 阿利伯克 / 悍马 / 爱国者",
            "背景：与那国岛 20 ℃\n发射率 0.95，软件温度范围 0–60 ℃",
            "两档传感器\n识别通道 IFOV 12.5 μrad / 搜索通道 63.9 μrad",
            "HITRAN2020 多温压逐线截面\n（220/250/280/300 K × 1.0/0.6/0.36/0.2 atm）\n+ 真实气候统计（NASA POWER / MERRA-2）",
        ],
    ),
    dict(
        title="模型链",
        color="#4338CA",
        leaves=[
            "斜程 τ(λ)（球面分层 + HITRAN 多温压逐线）\n+ 气溶胶 Ångström 消光 + 分子散射",
            "目标 / 背景辐亮度\nPlanck 发射 + 反射项 (1−ε)·B(T_bg)",
            "视在温差 ΔT_app = ε_t·ΔB 加权\n（权重参考温度取背景温度）",
            "MTF 链：衍射 · 探测器 sinc\n· 视线抖动 · 湍流 · 电子学",
            "MRTD(f) = k·NETD / MTF(f)\n→ f_max（Nyquist / 衍射 / 对比度 三重限）",
            "N = f_max·θ → TTPF 概率\nP = (N/N50)^E / [1 + (N/N50)^E]",
        ],
    ),
    dict(
        title="三类极限",
        color="#B45309",
        leaves=[
            "① 分辨率天花板 R_res\n= f_upper·D_eff / N50",
            "② 对比度地板\nτ_opt·ΔT_app <= k·NETD 时 f_max = 0，任何距离都不可识别",
            "③ 湍流边界\nCn² 增大 → r0 减小 → MTF_turb 下降 → f_max 提前截止",
            "实际 R50 = 三类边界竞争结果\n折减比 η = R50 / R_res 度量被大气/湍流削掉多少",
        ],
    ),
    dict(
        title="实验设计",
        color="#7E22CE",
        leaves=[
            "15 组严格 OFAT（S01–S15）\n目标 / 波段 / 热状态 / AOD / α / PWV / Cn² / 口径 /\nNETD / IFOV / 平台高度 / 判据 / 尺寸口径 / 发射率 / 工作模式",
            "8 类真实环境 × p10 / 中位 / p90\n沙漠 / 沙尘 / 半干旱 / 农田 / 城市 / 近岸 / 海洋 / 高原",
            "临界状态反解\nR50/R90、AOD_crit、Cn²_crit、D_crit、NETD_crit、ΔT 盲区",
        ],
    ),
    dict(
        title="数据产品",
        color="#15803D",
        leaves=[
            "全工况长表 eval_long.csv.gz\n每个（工况, 目标, 距离）一行的完整链路量",
            "S00–S15 单变量汇总表\n每组一个 CSV，支持任意横向对比",
            "临界状态汇总表 / 真实气候工况表\n可复算的临界参数与环境分位结果",
            "识别极限_数据汇总.xlsx\n各扫描独立 sheet，便于查阅",
        ],
    ),
    dict(
        title="图件体系",
        color="#0369A1",
        leaves=[
            "图01 模型链路与三类极限\n图02 工况空间与默认工况定位",
            "图03 斜程大气光谱透过率（MWIR/LWIR 多工况）\n图04 MTF 链与 MRTD",
            "图05–06 概率曲线 / 三任务临界距离\n图07–11 单变量族（AOD、Cn²、热状态、传感器、平台高度）",
            "图12 波段对比 · 图13 识别极限包络\n图14/15 相图（AOD×Cn²、ΔT×AOD）\n图16 真实气候热力图 · 图17 敏感性",
        ],
    ),
    dict(
        title="校验与不确定度",
        color="#9F1239",
        leaves=[
            "V&V 检查\nτ 极限 / L_path 界限 / ΔT_app 上限 / 单调性 /\n解析-数值一致 / 长表-汇总一致",
            "公式校准\nPlanck 与 dB/dT、权重参考温度、ISO 2533 廓线、\n地球曲率、Rayleigh 口径、发射率反射项",
            "主要不确定度\nN50 双口径（约 2 倍）、MRTD 系数 k=2.5、目标包围盒未标定",
            "已知缺口\n水汽连续吸收（MT_CKD）未含、传感器参数为设定值、Cn² 均匀",
        ],
    ),
    dict(
        title="结论要点",
        color="#A16207",
        leaves=[
            "小目标：分辨率锁死\n识别距离由采样与判据决定，η ≈ 0.95–1.00",
            "大目标：大气锁死\n识别距离由大气透过率决定，η ≈ 0.34–0.44",
            "湍流是第三边界\nCn² >= 1e-14 后开始主导，可致小目标不可识别",
            "热交叉盲区\nΔT→0 时对比度严格为零；存在由 NETD 地板\n决定的窄盲区（宽度量级约 1 K，随距离变化）",
            "波段选择看匹配\nMWIR 采样受限、LWIR 衍射受限；长波不等于更适合识别",
        ],
    ),
]

# --------------------------------------------------------------------------- #
# 排版工具
# --------------------------------------------------------------------------- #
def _char_units(s: str) -> float:
    """显示宽度（单位：字宽）。中日韩字符记 1.0，西文/数字记 0.62。"""
    return sum(1.0 if ord(ch) > 0x2E80 else 0.62 for ch in s)


def wrap_text(text: str, max_units: float):
    """按显示宽度折行（尊重显式换行）；ASCII 词组（如 f_max、NETD_crit）不拆开。"""
    token_re = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/%^\-+()\[\]<>·]*|\s+|.")
    lines = []
    for seg in str(text).split("\n"):
        seg = seg.strip()
        if not seg:
            continue
        cur, cur_w = "", 0.0
        for tok in token_re.findall(seg):
            if tok.isspace():
                if cur and not cur.endswith(" "):
                    cur += " "
                    cur_w += 0.45
                continue
            tok_w = sum(0.62 if ord(ch) <= 0x2E80 else 1.0 for ch in tok)
            if cur_w + tok_w > max_units and cur.strip():
                lines.append(cur.rstrip())
                cur, cur_w = tok, tok_w
            elif tok_w > max_units:                     # 超长西文串：硬拆
                for ch in tok:
                    w = 0.62 if ord(ch) <= 0x2E80 else 1.0
                    if cur_w + w > max_units and cur.strip():
                        lines.append(cur.rstrip())
                        cur, cur_w = ch, w
                    else:
                        cur += ch
                        cur_w += w
            else:
                cur += tok
                cur_w += tok_w
        if cur.strip():
            lines.append(cur.rstrip())
    return lines


def _blend(color: str, other: str = "#FFFFFF", k: float = 0.92):
    """把 color 按比例 k 混向 other（k=0 原色，k=1 全白）。"""
    c = mcolors.to_rgb(color)
    o = mcolors.to_rgb(other)
    return tuple(c[i] * (1 - k) + o[i] * k for i in range(3))


def _rounded(ax, cx, cy, w, h, face, edge, lw=1.0, radius=0.10, alpha=1.0, z=2):
    patch = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=face, edgecolor=edge, linewidth=lw, alpha=alpha, zorder=z,
    )
    ax.add_patch(patch)
    return patch


def _curve(ax, p0, p1, color, lw=1.15, alpha=0.72, z=1):
    """两点之间的水平三次贝塞尔连接线。"""
    x0, y0 = p0
    x1, y1 = p1
    dx = (x1 - x0)
    c0 = (x0 + dx * 0.45, y0)
    c1 = (x1 - dx * 0.45, y1)
    path = Path([p0, c0, c1, p1], [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
    ax.add_patch(PathPatch(path, facecolor="none", edgecolor=color,
                           lw=lw, alpha=alpha, zorder=z, capstyle="round"))


# --------------------------------------------------------------------------- #
# 版式参数
# --------------------------------------------------------------------------- #
STYLE = {
    "square": dict(LEAF_W=3.25, LEAF_MIN_W=1.95, BRANCH_W=1.80, ROOT_W=2.75,
                   GAP_BL=0.32, GAP_RB=0.42, GROUP_GAP=0.34, LEAF_GAP=0.085,
                   MARGIN_X=0.30, MARGIN_Y=0.32,
                   leaf_fs=9.8, branch_fs=13.0, root_fs=20.0,
                   aspect=None),
    "wide": dict(LEAF_W=4.30, LEAF_MIN_W=2.40, BRANCH_W=2.00, ROOT_W=3.20,
                 GAP_BL=0.55, GAP_RB=None, GROUP_GAP=0.32, LEAF_GAP=0.090,
                 MARGIN_X=0.45, MARGIN_Y=0.40,
                 leaf_fs=10.2, branch_fs=13.5, root_fs=21.0,
                 aspect=1.80),
}


# --------------------------------------------------------------------------- #
# 主绘制
# --------------------------------------------------------------------------- #
def build(mode: str = "square"):
    st = dict(STYLE[mode])
    branch_h = 0.62
    MARGIN_X, MARGIN_Y = st["MARGIN_X"], st["MARGIN_Y"]
    LEAF_W, LEAF_MIN_W = st["LEAF_W"], st["LEAF_MIN_W"]
    BRANCH_W, ROOT_W = st["BRANCH_W"], st["ROOT_W"]
    GAP_BL = st["GAP_BL"]
    GROUP_GAP, LEAF_GAP = st["GROUP_GAP"], st["LEAF_GAP"]
    leaf_fs, branch_fs, root_fs = st["leaf_fs"], st["branch_fs"], st["root_fs"]

    char_in = leaf_fs / 72.0
    line_h = leaf_fs / 72.0 * 1.34
    max_units = (LEAF_W - 0.36) / char_in

    # ---- 精确测量文本宽度的临时画布（72 dpi 时 1 像素 = 1 点）----
    meas_fig = plt.figure(figsize=(1, 1), dpi=72)
    meas_renderer = meas_fig.canvas.get_renderer()

    def measure_lines(lines):
        width_in = 0.0
        for line in lines:
            artist = meas_fig.text(0.0, 0.5, line, fontsize=leaf_fs, fontfamily=FONT)
            bbox = artist.get_window_extent(renderer=meas_renderer)
            width_in = max(width_in, bbox.width / 72.0)
            artist.remove()
        return width_in

    # ---- 预排版：折行并计算每个条目的宽高 ----
    wrapped = []
    for br in BRANCHES:
        items = []
        for text in br["leaves"]:
            mu = max_units
            lines = wrap_text(text, mu)
            text_w = LEAF_W
            for _ in range(6):
                text_w = measure_lines(lines)
                if text_w + 0.36 <= LEAF_W or mu < 9.0:
                    break
                mu *= 0.93
                lines = wrap_text(text, mu)
            # 若末行只剩一两个字，尝试略放宽以消除孤字行
            if len(lines) > 1 and _char_units(lines[-1]) < 3.2:
                for bump in (1.05, 1.10, 1.16):
                    cand = wrap_text(text, mu * bump)
                    if len(cand) < len(lines):
                        cand_w = measure_lines(cand)
                        if cand_w + 0.36 <= LEAF_W:
                            lines, text_w = cand, cand_w
                            break
            h = 0.15 + line_h * len(lines)
            w = min(LEAF_W, max(LEAF_MIN_W, text_w + 0.36))
            items.append(dict(lines=lines, w=w, h=h))
        wrapped.append(dict(title=br["title"], color=br["color"], items=items))
    plt.close(meas_fig)

    def group_content_h(br):
        return sum(it["h"] for it in br["items"]) + LEAF_GAP * (len(br["items"]) - 1)

    def side_height(branch_list):
        total = 0.0
        for i, br in enumerate(branch_list):
            total += max(group_content_h(br), branch_h)
            if i < len(branch_list) - 1:
                total += GROUP_GAP
        return total

    # 左右分栏：右侧放叙事主线（问题→输入→模型→极限→实验），左侧放产出（数据→图件→校验→结论）
    n_right = 5
    right_side = wrapped[:n_right]
    left_side = wrapped[n_right:]

    h_left, h_right = side_height(left_side), side_height(right_side)
    canvas_h = max(h_left, h_right) + 2 * MARGIN_Y

    if st["aspect"] is None:
        inner_w = LEAF_W + GAP_BL + BRANCH_W + st["GAP_RB"] + ROOT_W / 2
        canvas_w = 2 * (MARGIN_X + inner_w)
        gap_rb = st["GAP_RB"]
    else:
        canvas_w = max(st["aspect"] * canvas_h, 12.0)
        gap_rb = (canvas_w / 2.0 - MARGIN_X - LEAF_W - GAP_BL - BRANCH_W - ROOT_W / 2.0)
        gap_rb = max(0.55, gap_rb)

    fig = plt.figure(figsize=(canvas_w, canvas_h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, canvas_w)
    ax.set_ylim(0, canvas_h)
    ax.axis("off")

    cx = canvas_w / 2.0
    cy = canvas_h / 2.0
    root_h = 1.05

    def layout_side(branch_list, side):
        total = side_height(branch_list)
        y = cy + total / 2.0
        out = []
        for br in branch_list:
            content_h = group_content_h(br)
            g_h = max(content_h, branch_h)
            top = y
            shift = (g_h - content_h) / 2.0
            yy = top - shift
            leaves = []
            for it in br["items"]:
                leaves.append((yy - it["h"] / 2.0, it))
                yy -= it["h"] + LEAF_GAP
            by = top - g_h / 2.0
            if side == "right":
                bx = cx + ROOT_W / 2.0 + gap_rb + BRANCH_W / 2.0
                leaf_x = bx + BRANCH_W / 2.0 + GAP_BL + LEAF_W / 2.0
                x0 = bx - BRANCH_W / 2.0 - 0.10
                x1 = leaf_x + LEAF_W / 2.0 + 0.10
            else:
                bx = cx - ROOT_W / 2.0 - gap_rb - BRANCH_W / 2.0
                leaf_x = bx - BRANCH_W / 2.0 - GAP_BL - LEAF_W / 2.0
                x0 = leaf_x - LEAF_W / 2.0 - 0.10
                x1 = bx + BRANCH_W / 2.0 + 0.10
            panel = dict(
                x0=x0, x1=x1,
                y0=min(min(p - it["h"] / 2.0 for p, it in leaves), by - branch_h / 2.0) - 0.12,
                y1=max(max(p + it["h"] / 2.0 for p, it in leaves), by + branch_h / 2.0) + 0.12,
            )
            out.append(dict(branch=br, bx=bx, by=by, leaf_x=leaf_x,
                            leaves=leaves, panel=panel))
            y -= g_h + GROUP_GAP
        return out

    laid_left = layout_side(left_side, "left")
    laid_right = layout_side(right_side, "right")

    # ---- 1) 分支底板（浅色分组）----
    for group in laid_left + laid_right:
        br = group["branch"]
        pb = group["panel"]
        _rounded(ax, (pb["x0"] + pb["x1"]) / 2, (pb["y0"] + pb["y1"]) / 2,
                 pb["x1"] - pb["x0"], pb["y1"] - pb["y0"],
                 face=_blend(br["color"], "#FFFFFF", 0.945),
                 edge=_blend(br["color"], "#FFFFFF", 0.55),
                 lw=0.9, radius=0.16, alpha=0.95, z=0)

    # ---- 2) 连接线 ----
    root_edge_r = (cx + ROOT_W / 2.0, cy)
    root_edge_l = (cx - ROOT_W / 2.0, cy)
    for group in laid_right:
        _curve(ax, root_edge_r, (group["bx"] - BRANCH_W / 2.0, group["by"]), group["branch"]["color"])
    for group in laid_left:
        _curve(ax, root_edge_l, (group["bx"] + BRANCH_W / 2.0, group["by"]), group["branch"]["color"])

    for group in laid_left + laid_right:
        side = "left" if group["bx"] < cx else "right"
        color = group["branch"]["color"]
        if side == "right":
            b_edge = (group["bx"] + BRANCH_W / 2.0, group["by"])
            for ly, it in group["leaves"]:
                _curve(ax, b_edge, (group["leaf_x"] - it["w"] / 2.0, ly), color, lw=0.95, alpha=0.62)
        else:
            b_edge = (group["bx"] - BRANCH_W / 2.0, group["by"])
            for ly, it in group["leaves"]:
                _curve(ax, b_edge, (group["leaf_x"] + it["w"] / 2.0, ly), color, lw=0.95, alpha=0.62)

    # ---- 3) 根节点 ----
    _rounded(ax, cx, cy, ROOT_W, root_h, face="#1F3A5F", edge="#12233A", lw=1.6, radius=0.16, z=4)
    ax.text(cx, cy, ROOT_TEXT, ha="center", va="center", color="white",
            fontsize=root_fs, fontweight="bold", linespacing=1.24, zorder=5)

    # ---- 4) 分支节点 ----
    for group in laid_left + laid_right:
        br = group["branch"]
        _rounded(ax, group["bx"], group["by"], BRANCH_W, branch_h,
                 face=br["color"], edge=_blend(br["color"], "#000000", 0.25),
                 lw=1.0, radius=0.12, z=4)
        ax.text(group["bx"], group["by"], br["title"], ha="center", va="center",
                color="white", fontsize=branch_fs, fontweight="bold", zorder=5)

    # ---- 5) 条目节点 ----
    for group in laid_left + laid_right:
        br = group["branch"]
        for ly, it in group["leaves"]:
            _rounded(ax, group["leaf_x"], ly, it["w"], it["h"],
                     face="white", edge=br["color"], lw=1.0, radius=0.085, z=3)
            ax.text(group["leaf_x"], ly, "\n".join(it["lines"]), ha="center", va="center",
                    color="#1A1A1A", fontsize=leaf_fs, linespacing=1.34, zorder=5)

    # ---- 6) 角注（不写任何版本信息）----
    ax.text(MARGIN_X, MARGIN_Y * 0.55,
            "项目思维导图 · 问题 → 输入 → 模型 → 实验 → 数据 → 图件 → 校验 → 结论",
            ha="left", va="center", fontsize=7.6, color="#7A7A7A", zorder=5)

    return fig


def _save(fig, name):
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.08, facecolor="white")
    print("[ok]", path, flush=True)
    return path


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    print("[progress 1/2] 标准版 ...", flush=True)
    fig = build("square")
    _save(fig, PNG_NAME)
    _save(fig, PDF_NAME)
    plt.close(fig)

    print("[progress 2/2] 横版 ...", flush=True)
    fig = build("wide")
    _save(fig, PNG_WIDE_NAME)
    _save(fig, PDF_WIDE_NAME)
    plt.close(fig)

    print("[ok] 字体:", FONT, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

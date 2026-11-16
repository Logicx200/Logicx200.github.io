# -*- coding: utf-8 -*-
"""实验 11：光学系统的光束限制 —— 孔径光阑、视场光阑、光瞳与窗。

对应考点（第九章）：
    1. 孔径光阑的判定：各光阑在物方的孔径角 u_i = (D_i/2)/|B_i|
    2. 入射光瞳 = 孔径光阑经**前面**系统所成的像；出射光瞳同理
    3. 视场光阑与入窗/出窗、渐晕
    4. 相对孔径 D/f' 与数值孔径 NA
运行：  python demos/d11_aperture_stop.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import geometrical as geo  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

# 系统：物在 L1 前 40 mm；L1(f=100, D=40)；间隔 60 mm；光阑 P(D=20)；L2(f=60)
sys_opt = geo.ParaxialSystem([
    {"type": "gap", "d": 0.04},                  # 物面 -> L1
    {"type": "lens", "f": 0.10, "semi": 0.02},   # L1
    {"type": "gap", "d": 0.06},
    {"type": "stop", "semi": 0.01},              # 光阑 P
    {"type": "gap", "d": 0.04},
    {"type": "lens", "f": 0.06, "semi": 0.015},  # L2
])
stop, data = sys_opt.aperture_stop()
ep = sys_opt.entrance_pupil()
xp = sys_opt.exit_pupil()
fstop, fdata = sys_opt.field_stop()
planes = dict(sys_opt.plane_positions())

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 判定依据柱状图
ax = axes[0, 0]
labels = [f"元件{i}\n({sys_opt.elements[i]['type']})" for i, _, _, _ in
          [(d["index"], 0, 0, 0) for d in data]]
us = [d["u_object"] for d in data]
colors = ["C3" if d["index"] == stop else "C0" for d in data]
ax.bar(range(len(us)), np.array(us) * 1e3, color=colors)
ax.set_xticks(range(len(us)))
ax.set_xticklabels(labels, fontsize=8)
ax.set_title("(a) 各光阑的物方孔径角 $u_i=(D_i/2)/|B_i|$\n最小者为孔径光阑")
ax.set_ylabel("物方孔径角 u / mrad")
for i, u in enumerate(us):
    ax.text(i, u * 1e3 * 1.02, f"{u*1e3:.1f}", ha="center", fontsize=8)

# ------------------------------------------------- (b) 光路与光瞳
ax = axes[0, 1]
ax.axhline(0, color="k", lw=0.8)
for z, idx in sys_opt.plane_positions():
    e = sys_opt.elements[idx]
    s = e.get("semi", 0.0)
    c = "C3" if idx == stop else ("C2" if e["type"] == "lens" else "C0")
    ax.plot([z * 1e3, z * 1e3], [-s * 1e3, s * 1e3], color=c, lw=2)
    ax.text(z * 1e3, s * 1e3 + 0.6, e["type"], fontsize=8, ha="center", color=c)

# 轴上物点的边缘光线（恰好充满孔径光阑）
u_edge = [d["u_object"] for d in data if d["index"] == stop][0]
for sgn in (+1, -1):
    pts = sys_opt.trace_ray(0.0, sgn * u_edge)
    zs = [p[0] * 1e3 for p in pts]
    ys = [p[1] * 1e3 for p in pts]
    ax.plot(zs, ys, "C1", lw=1)
# 入射光瞳与出射光瞳位置
ax.axvline(ep["position"] * 1e3, color="C4", lw=1, ls="--")
ax.axvline(0, color="gray", lw=0.8, ls=":")
ax.plot(ep["position"] * 1e3, 0, "v", color="C4", ms=9)
ax.plot(ep["position"] * 1e3, ep["diameter"] * 1e3 / 2, "_", color="C4", ms=12)
ax.plot(ep["position"] * 1e3, -ep["diameter"] * 1e3 / 2, "_", color="C4", ms=12)
ax.annotate(f"入射光瞳 φ{ep['diameter']*1e3:.1f} mm\n(相对物面 {ep['position']*1e3:+.0f} mm)",
            (ep["position"] * 1e3, ep["diameter"] * 1e3 / 2),
            textcoords="offset points", xytext=(24, 8), fontsize=8, color="C4")
ax.set_title(f"(b) 光路图：孔径光阑=元件{stop}；绿线为充满光阑的边缘光线")
ax.set_xlabel("轴向位置 / mm（物面为 0）")
ax.set_ylabel("高度 / mm")
ax.set_xlim(-215, 200)
ax.set_ylim(-32, 30)

# ------------------------------------------------- (c) 视场光阑判定
ax = axes[1, 0]
if fdata:
    idxs = [d["index"] for d in fdata]
    hs = [d["object_height"] * 1e3 for d in fdata]
    cols = ["C3" if i == fstop else "C0" for i in idxs]
    ax.bar(range(len(hs)), hs, color=cols)
    ax.set_xticks(range(len(hs)))
    ax.set_xticklabels([f"元件{i}" for i in idxs], fontsize=8)
    for i, h in enumerate(hs):
        ax.text(i, h * 1.02, f"{h:.2f}", ha="center", fontsize=8)
    ax.set_title(f"(c) 各光阑允许的最大物高（主光线判据）\n最小者 = 视场光阑：元件 {fstop}")
    ax.set_ylabel("最大物高 y / mm")
else:
    ax.text(0.5, 0.5, "无独立视场光阑（视场由物镜口径决定）",
            ha="center", va="center", transform=ax.transAxes)

# ------------------------------------------------- (d) 渐晕曲线
ax = axes[1, 1]
M_stop = [d["M"] for d in data if d["index"] == stop][0]
u_m = [d["u_object"] for d in data if d["index"] == stop][0]
As, Bs = M_stop[0, 0], M_stop[0, 1]
apertures = sys_opt.apertures()
y0s = np.linspace(0, 60, 300) * 1e-3


def vignetting(y0, n=241):
    """返回边缘光束中仍能全部通过各光阑的比例（渐晕系数 K）。"""
    u_chief = -As * y0 / Bs
    us = np.linspace(u_chief - u_m, u_chief + u_m, n)
    ok = 0
    for u in us:
        if all(abs(M[0, 0] * y0 + M[0, 1] * u) <= semi + 1e-12
               for _, M, semi, _ in apertures):
            ok += 1
    return ok / n


Ks = np.array([vignetting(y) for y in y0s])
ax.plot(y0s * 1e3, Ks, "C0", lw=1.4)
ax.fill_between(y0s * 1e3, Ks, color="C0", alpha=0.15)
ax.axhline(0.5, color="r", ls=":", lw=0.9)
ax.text(1, 0.52, "K = 0.5（允许渐晕界限）", color="r", fontsize=8)
i50 = np.argmax(Ks < 0.5)
if Ks[i50] < 0.5:
    ax.axvline(y0s[i50] * 1e3, color="r", ls="--", lw=1)
    ax.text(y0s[i50] * 1e3 + 1, 0.85, f"物高 {y0s[i50]*1e3:.1f} mm\n开始明显渐晕",
            color="r", fontsize=8)
ax.set_title("(d) 渐晕曲线：$K$ = 边缘光束能通过的比例")
ax.set_xlabel("物高 y / mm")
ax.set_ylabel("渐晕系数 K")
ax.set_ylim(0, 1.08)

fig.suptitle("光束限制：孔径光阑与视场光阑（第九章）", fontsize=13)
save_fig(fig, "d11_aperture_stop.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
for d in data:
    print(f"  元件 {d['index']} ({sys_opt.elements[d['index']]['type']}): "
          f"半口径 {d['semi']*1e3:5.2f} mm, 物方孔径角 u = {d['u_object']*1e3:8.3f} mrad")
print(f"→ 孔径光阑：元件 {stop}")
print(f"  入射光瞳：位置 {ep['position']*1e3:+.2f} mm（相对物面，向左为正），"
      f"直径 {ep['diameter']*1e3:.2f} mm")
print(f"  出射光瞳：位置 {xp['position']*1e3:+.2f} mm（相对系统最后一面，向右为正；"
      f"负值表示是虚光瞳、位于系统内部）")
print(f"            直径 {xp['diameter']*1e3:.2f} mm")
if fdata:
    print(f"→ 视场光阑：元件 {fstop}，物方最大物高 {[d['object_height'] for d in fdata if d['index']==fstop][0]*1e3:.3f} mm")
print(f"\nL1 相对孔径 D/f' = {2*0.02/0.10:.3f}（即 f/2.5）")
print(f"数值孔径 NA = n sin u = {np.sin(0.02/abs(ep['position'])):.4f}"
      f"（用物方最大孔径角 u={0.02/abs(ep['position']):.4f} rad 近似）")
print("\n解题模板（第九章必考）：")
print("  1) 把每个光阑的直径、位置列成表")
print("  2) 算出前置系统对每个光阑的像（位置 + 放大率）")
print("  3) 比较各像对轴上物点张角，最小者 → 孔径光阑；其像即入射/出射光瞳")
print("  4) 视场光阑用“主光线（过入射光瞳中心）是否被拦”来判定")

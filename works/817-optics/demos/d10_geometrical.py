# -*- coding: utf-8 -*-
"""实验 10：几何光学 —— 近轴光路、理想光学系统、球差。

对应考点（第七、八、九章）：
    1. 符号规则与近轴光路计算（y-u 递推）
    2. 理想光学系统的基点基面、图解法与解析法
    3. 双光组组合公式与近轴矩阵的一致性
    4. 实际光线追迹求球差：边缘光线焦点比近轴焦点更近
运行：  python demos/d10_geometrical.py
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

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 薄透镜作图法
ax = axes[0, 0]
f = 100.0
u_obj = 2 * f
v_img = geo.gauss_image(u_obj, f)
ax.axhline(0, color="k", lw=1)
ax.axvline(0, color="gray", lw=1)
for zz, lab in [(-f, "F"), (f, "F'"), (-2 * f, "2F"), (2 * f, "2F'")]:
    ax.plot([zz], [0], "k|", ms=10)
    ax.annotate(lab, (zz, 0), textcoords="offset points", xytext=(0, -16),
                ha="center", fontsize=9)
ax.plot([-u_obj], [0], "o", color="C3")
ax.annotate("物", (-u_obj, 0), textcoords="offset points", xytext=(0, 8),
            ha="center", color="C3")
ax.plot([v_img], [0], "o", color="C0")
ax.annotate("像", (v_img, 0), textcoords="offset points", xytext=(0, 8),
            ha="center", color="C0")
h = 30.0
h3 = -h * f / (u_obj - f)                      # 过 F 的光线在透镜上的高度
ax.annotate("", (-u_obj, 0), (-u_obj, h), arrowprops=dict(arrowstyle="->", color="C3"))
ax.annotate("", (v_img, 0), (v_img, -h), arrowprops=dict(arrowstyle="->", color="C0"))
for pts in [
    [(-u_obj, h), (0, h), (f, 0), (v_img, -h)],   # 平行光轴 → 过 F'
    [(-u_obj, h), (0, 0), (v_img, -h)],           # 过光心，方向不变
    [(-u_obj, h), (0, h3), (v_img, h3)],          # 过 F → 出射平行光轴
]:
    zs, ys = zip(*pts)
    ax.plot(zs, ys, "C0", lw=1)
ax.plot(0, 0, "ks", ms=3)
ax.set_ylim(-45, 45)
ax.set_xlim(-1.6 * u_obj, 1.6 * v_img)
ax.set_title(f"(a) 薄透镜作图法：物在 2F，像在 2F'，β={geo.transverse_magnification(-u_obj, v_img):.2f}")
ax.set_xlabel("轴向位置 / mm")
ax.set_ylabel("高度 / mm")

# ------------------------------------------------- (b) 球差：实际光线追迹
ax = axes[0, 1]
r_s, n1, n2 = 50.0, 1.0, 1.5
hs = np.linspace(0.2, 24.0, 200)
l_par = geo.paraxial_focus_sphere(r_s, n1, n2)
l_h = np.array([geo.spherical_aberration_focus(h, r_s, n1, n2) for h in hs])
ax.plot(hs, l_h, label="实际光线与光轴交点 $l'_h$")
ax.axhline(l_par, color="r", ls="--", label=f"近轴焦点 $l'={l_par:.1f}$ mm")
ax.fill_between(hs, l_h, l_par, color="C0", alpha=0.15)
ax.annotate("轴向球差 $\\delta L'$", (15, (l_h[80] + l_par) / 2), color="C0", fontsize=10)
ax.set_title(f"(b) 单折射面球差（r={r_s:.0f} mm, n=1.5）")
ax.set_xlabel("入射高度 h / mm")
ax.set_ylabel("与光轴交点到顶点的距离 / mm")
ax.legend(fontsize=8)

# ------------------------------------------------- (c) 双光组组合
ax = axes[1, 0]
f1, f2 = 100.0, -60.0
ds = np.linspace(1.0, 250.0, 600)
f_comb = np.array([geo.two_lens_combination(f1, f2, d)["f"] for d in ds])
f_mat = np.array([geo.two_lens_combination_from_matrix(f1, f2, d)["f"] for d in ds])
ax.plot(ds, f_comb, label="双光组组合公式")
ax.plot(ds[::40], f_mat[::40], "o", ms=4, label="近轴矩阵（数值验证）")
ax.axhline(0, color="k", lw=0.8)
ax.axvline(f1 + f2, color="r", ls=":", lw=1)
ax.text(f1 + f2 + 4, 400, f"d = f1'+f2 = {f1+f2:.0f} mm\n（望远镜：无焦系统）",
        color="r", fontsize=8)
ax.set_title(f"(c) 双光组组合 f'={f1:.0f} mm 与 {f2:.0f} mm")
ax.set_xlabel("光组间隔 d / mm")
ax.set_ylabel("组合焦距 f' / mm")
ax.set_ylim(-600, 900)
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 成像公式
ax = axes[1, 1]
u = np.linspace(1.2 * f, 8 * f, 800)
v = geo.gauss_image(u, f)
beta = -v / u
ax.plot(u / f, v / f, label="高斯公式 $1/v+1/u=1/f$")
ax.plot(u / f, np.abs(beta), "--", label="|β| = v/u")
ax.axvline(2, color="r", ls=":", lw=0.8)
ax.text(2.05, 3.0, "u=2f → v=2f, |β|=1\n（物像等大）", fontsize=8, color="r")
ax.set_ylim(0, 8)
ax.set_xlim(1, 8)
ax.set_title("(d) 成像公式：物距-像距曲线与放大率")
ax.set_xlabel("物距 u / f")
ax.set_ylabel("v / f  或  |β|")
ax.legend(fontsize=8)

fig.suptitle("几何光学与理想光学系统（第七、八、九章）", fontsize=13)
save_fig(fig, "d10_geometrical.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
l, r0, nn1, nn2 = -300.0, 100.0, 1.0, 1.5
lp, bb = geo.refraction_sphere(l, r0, nn1, nn2)
print(f"单折射球面 r={r0} mm, n={nn1}->{nn2}, 物距 l={l} mm：")
print(f"  l' = {lp:.2f} mm, β = {bb:.4f}")
print(f"  满足 n'/l' - n/l = {nn2/lp - nn1/l:.8f} = (n'-n)/r = {(nn2-nn1)/r0:.8f}")
print(f"\n单折射面球差（r={r_s} mm, n=1.5）：")
for h in (5, 10, 20):
    print(f"  h={h:2d} mm: l'_h = {geo.spherical_aberration_focus(h, r_s, n1, n2):.3f} mm, "
          f"球差 δL' = {geo.spherical_aberration_focus(h, r_s, n1, n2)-l_par:+.3f} mm")
print(f"\n双光组（f1'=100 mm, f2'=-60 mm）：")
for d in (40, 100, 160):
    a = geo.two_lens_combination(100, -60, d)
    print(f"  d={d:3d} mm: f' = {a['f']:8.3f} mm, l_F' = {a['lFp']:8.3f} mm（公式）")
print("\n考点提醒：球差、色差、正弦差等像差都是“实际光线偏离近轴理想成像”的结果；")
print("          用实际光线追迹（refract_sphere_real）和近轴公式（refraction_sphere）")
print("          各算一遍，差值就是像差，这是最不容易记混的方法。")

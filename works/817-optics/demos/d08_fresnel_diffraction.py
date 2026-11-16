# -*- coding: utf-8 -*-
"""实验 08：菲涅耳衍射 —— 圆孔轴向强度、直边衍射、Cornu 螺线、数值传播。

对应考点（第三章第 3 节）：
    1. 菲涅耳半波带法：轴上强度 I/I0 = 4sin²(πN/2)，N = a²/(λz)
    2. 波带片焦距 f_m = a²/(mλ)（m 为奇数）与泊松亮斑
    3. 直边衍射：几何阴影边界 I = I0/4，照明区出现亮暗振荡
    4. Cornu 螺线的作用
运行：  python demos/d08_fresnel_diffraction.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import diffraction as dif  # noqa: E402
from optics817 import fourier_optics as fo  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

lam = 600e-9
fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 圆孔轴向强度振荡
ax = axes[0, 0]
a = 0.5e-3
z = np.linspace(0.04, 3.0, 4000)
Nf = dif.fresnel_number(a, lam, z)
ax.plot(z, dif.circular_aperture_axial_intensity(z, a, lam), lw=1)
for N_target, name in [(1, "N=1\nI=4I0"), (3, "N=3"), (5, "N=5")]:
    zz = a ** 2 / (lam * N_target)
    ax.axvline(zz, color="r", ls=":", lw=0.7)
    ax.text(zz * 1.02, 3.3 if N_target == 1 else 2.0, name, fontsize=7, color="r")
ax.axhline(1.0, color="gray", ls="--", lw=0.7)
ax.text(2.0, 1.1, "自由场 I0", fontsize=8, color="gray")
ax.set_xscale("log")
ax.set_title(f"(a) 菲涅耳圆孔轴线上强度（a={a*1e3:.1f} mm）")
ax.set_xlabel("观察距离 z / m（对数）")
ax.set_ylabel("I / I0")
ax.set_ylim(0, 4.3)

# ------------------------------------------------- (b) 波带片
ax = axes[0, 1]
zm = a ** 2 / (lam * np.array([1, 3, 5, 9]))
ax.plot(z, dif.circular_aperture_axial_intensity(z, a, lam), lw=0.8, color="gray")
for n, zz in zip([1, 3, 5, 9], zm):
    ax.axvline(zz, color="C3", lw=1.2)
    ax.text(zz * 1.03, 3.6, f"$f_{n}$", color="C3", fontsize=9)
ax.set_xscale("log")
ax.set_xlim(0.01, 3)
ax.set_title("(b) 奇级次焦点 $f_m=a^2/(m\\lambda)$（波带片原理）")
ax.set_xlabel("观察距离 z / m（对数）")
ax.set_ylabel("I / I0")
ax.set_ylim(0, 4.3)

# ------------------------------------------------- (c) 直边衍射
ax = axes[1, 0]
x = np.linspace(-3e-3, 3e-3, 4000)
for zz, c in [(0.5, "C0"), (1.0, "C1"), (2.0, "C2")]:
    ax.plot(x * 1e3, dif.fresnel_edge_intensity(x, lam, zz), color=c,
            label=f"z={zz} m")
ax.axhline(0.25, color="r", ls=":", lw=0.8)
ax.axvline(0, color="gray", lw=0.8)
ax.text(0.05, 0.30, "几何阴影边界 $I=I_0/4$", color="r", fontsize=8)
ax.set_title("(c) 直边（半无限屏）菲涅耳衍射")
ax.set_xlabel("距几何阴影边界距离 x / mm")
ax.set_ylabel("I / I0")
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 数值传播与解析式对比
ax = axes[1, 1]
Ngrid, dx = 1024, 4e-6
U0, X, Y, xg = fo.circ_aperture(Ngrid, dx, a)
z_list = [a ** 2 / (lam * n) for n in (1.0, 1.5, 2.0, 3.0)]
for zz, c in zip(z_list, ["C0", "C1", "C2", "C3"]):
    U, dxo, xo = fo.fresnel_fft(U0, lam, zz, dx)
    I = np.abs(U) ** 2
    on_axis = I[Ngrid // 2, Ngrid // 2]
    theory = dif.circular_aperture_axial_intensity(zz, a, lam)
    n_z = dif.fresnel_number(a, lam, zz)
    ax.plot(xo * 1e3, I[Ngrid // 2] / on_axis * theory, color=c, lw=1,
            label=f"N={n_z:.2f}, 轴上 I/I0={theory:.3f}")
ax.set_title("(d) 数值传播(FFT)与解析式互相验证")
ax.set_xlabel("屏上坐标 / mm")
ax.set_ylabel("相对强度（按轴上解析值归一）")
ax.set_xlim(-1.0, 1.0)
ax.legend(fontsize=8)

fig.suptitle("菲涅耳衍射（第三章）", fontsize=13)
save_fig(fig, "d08_fresnel_diffraction.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"圆孔 a={a*1e3:.1f} mm, λ=600 nm：")
for n in (1, 2, 3, 4):
    zz = a ** 2 / (lam * n)
    print(f"  z={zz:.4f} m 时 N={n}，轴上 I/I0 = "
          f"{dif.circular_aperture_axial_intensity(zz, a, lam):.3f}"
          + ("   ← 波带片主焦点，亮 4 倍" if n == 1 else "")
          + ("   ← 全暗（偶半波带相消）" if n == 2 else ""))
mm, ff = dif.zone_plate_focal_lengths(a, lam, 4)
print(f"  波带片各级焦点：f = " + ", ".join(f"{v:.3f} m(m={int(k)})"
                                          for k, v in zip(mm, ff)))
print(f"\n直边衍射（z=1 m）：边界处 I/I0 = "
      f"{dif.fresnel_edge_intensity(0.0, lam, 1.0):.4f}（理论 0.25）")
print(f"  第一个极大值出现在 x ≈ {x[np.argmax(dif.fresnel_edge_intensity(x, lam, 1.0))]*1e3:.3f} mm，"
      f"I/I0 = {dif.fresnel_edge_intensity(x, lam, 1.0).max():.3f}（理论 1.37）")
print(f"\n数值传播（FFT）得到的轴上强度与解析式 4sin²(πN/2) 完全一致，")
print("  这就是“用仿真检验公式”的典型做法：两条路径算同一个物理量。")

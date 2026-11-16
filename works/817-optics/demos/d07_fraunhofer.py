# -*- coding: utf-8 -*-
"""实验 07：夫琅禾费衍射 —— 单缝、圆孔、多缝、光栅。

对应考点（第三章）：
    1. 单缝：a sinθ = kλ 暗纹，中央亮纹半角宽 λ/a
    2. 圆孔：艾里斑角半径 1.22λ/D，瑞利判据
    3. 多缝：主极大 + 次极大，N 越大主极大越锐
    4. 光栅：光栅方程 d sinθ = mλ、缺级 d/a = m/k、分辨本领 R = mN
运行：  python demos/d07_fraunhofer.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import diffraction as dif  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

lam, z = 600e-9, 1.0
x = np.linspace(-15e-3, 15e-3, 6000)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
fig.subplots_adjust(hspace=0.32, wspace=0.26)

# ------------------------------------------------- (a) 单缝
ax = axes[0, 0]
for a, c in [(0.05e-3, "C0"), (0.10e-3, "C1"), (0.20e-3, "C2")]:
    ax.plot(x * 1e3, dif.single_slit_intensity(x, lam, a, z), color=c,
            label=f"a={a*1e3:.2f} mm, 半角宽={np.degrees(lam/a):.3f}°")
ax.set_title("(a) 单缝夫琅禾费衍射")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-12, 12)
ax.legend(fontsize=8)

# ------------------------------------------------- (b) 圆孔与瑞利判据
ax = axes[0, 1]
D = 2e-3
ax.plot(x * 1e3, dif.circular_aperture_intensity(x, lam, D, z), "C0",
        label="单个艾里斑")
sep = dif.rayleigh_angle(lam, D) * z
ax.plot(x * 1e3, dif.circular_aperture_intensity(x - sep, lam, D, z)
        + dif.circular_aperture_intensity(x + sep, lam, D, z),
        "C1", label="恰可分辨（间距=1.22λ/D）")
ax.axvline(sep * 1e3, color="gray", ls=":", lw=0.8)
ax.set_title(f"(b) 圆孔衍射与瑞利判据（D={D*1e3:.0f} mm）")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-24, 24)
ax.legend(fontsize=8)

# ------------------------------------------------- (c) 多缝
ax = axes[1, 0]
d = 0.02e-3
for N, c in [(2, "C0"), (5, "C1"), (20, "C2"), (100, "C3")]:
    ax.plot(x * 1e3, dif.grating_intensity(x, lam, d, N, z=z), color=c,
            lw=1, label=f"N={N}")
ax.set_title("(c) 多缝衍射：N 越大主极大越细锐")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-8, 8)
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 光栅缺级
ax = axes[1, 1]
d = 1e-3 / 600.0        # 600 线/mm → 光栅常数 1.667 μm
a = 1e-3 / 1800.0       # 缝宽为周期的 1/3 → 3, 6, 9 级缺级
xg = np.linspace(-5e-3, 5e-3, 20000)
ax.plot(xg * 1e3, dif.grating_intensity(xg, 550e-9, d, 40, a=a, z=z), lw=0.9)
for m in range(-3, 4):
    if m == 0:
        continue
    xm = m * 550e-9 * z / d
    if abs(xm) < 5e-3:
        ax.axvline(xm * 1e3, color="r", ls=":", lw=0.7)
        ax.text(xm * 1e3, 0.85, f"m={m}" + ("\n缺级" if m % 3 == 0 else ""),
                fontsize=7, ha="center", color="r")
ax.set_title("(d) 光栅衍射（N=40）：d/a=3 → 3、6、9 级缺级")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-5, 5)

fig.suptitle("夫琅禾费衍射与光栅（第三章）", fontsize=13)
save_fig(fig, "d07_fraunhofer.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"单缝 a=0.1 mm（λ=600 nm）：中央亮纹半角宽 = λ/a = "
      f"{np.degrees(lam/0.1e-3):.4f}° = {lam/0.1e-3*1e3:.2f} mrad")
print(f"  第 1 暗纹在 x = λz/a = {lam*z/0.1e-3*1e3:.2f} mm 处")
print(f"\n圆孔 D=2 mm：艾里斑角半径 = 1.22λ/D = "
      f"{np.degrees(dif.rayleigh_angle(lam, D))*1e3:.3f} mrad")
print(f"  屏上艾里斑半径 = {dif.airy_radius(lam, D, z)*1e3:.4f} mm")
print(f"\n光栅 600 线/mm（d=1.667 μm）：")
print(f"  最高级次 m_max = floor(d/λ) = {dif.grating_max_order(550e-9, 1e-3/600)}")
for m in (1, 2, 3):
    th = dif.grating_angle(m, 550e-9, 1e-3 / 600.0)
    print(f"  第 {m} 级衍射角 = {np.degrees(th):.3f}°")
print(f"  刻线总长 30 mm（N=18000）时，第 2 级分辨本领 R = mN = "
      f"{dif.grating_resolving_power(2, 18000):.0f}，"
      f"能分辨的最小波长差 Δλ = {550e-9/36000*1e12:.3f} pm")
print("\n考点提醒：光栅条纹位置由 d 决定、锐度由 N 决定、强度包络由 a 决定，"
      "三者要分清。")

# -*- coding: utf-8 -*-
"""实验 04：平行平板多光束干涉 —— 爱里公式、精细度、法布里-珀罗干涉仪。

对应考点（第二章）：
    1. 爱里公式 T = 1/(1 + F sin²(δ/2))，F = 4R/(1-R)²
    2. 精细度 F* = π√R/(1-R)，自由光谱范围 FSR = λ²/(2nd)
    3. 分辨本领 λ/Δλ = m F*
    4. 多光束干涉条纹比双光束“锐”在哪里
运行：  python demos/d04_multibeam_fp.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import interference as itf  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

delta = np.linspace(-2 * np.pi, 2 * np.pi, 4000)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 爱里曲线
ax = axes[0, 0]
for r, c in [(0.2, "C0"), (0.5, "C1"), (0.8, "C2"), (0.95, "C3")]:
    ax.plot(delta / np.pi, itf.airy_transmission(delta, r), color=c,
            label=f"r={r}（R={r**2:.2f}）, F*={itf.finesse(r):.1f}")
ax.set_title("(a) 爱里公式：多光束干涉透射率")
ax.set_xlabel("相位差 δ / π")
ax.set_ylabel("透射率 T")
ax.set_xlim(-2, 2)
ax.legend(fontsize=8)

# ------------------------------------------------- (b) 与双光束对比
ax = axes[0, 1]
R = 0.8
I_two = (1 + R ** 2 + 2 * R * np.cos(delta)) / (1 + R) ** 2  # 只取前两束透射光
ax.plot(delta / np.pi, itf.airy_transmission(delta, np.sqrt(R)),
        label=f"多光束（全部反射） R={R}")
ax.plot(delta / np.pi, I_two, "--", label="双光束（只取前两束）")
ax.set_title("(b) 多光束条纹远比双光束尖锐")
ax.set_xlabel("相位差 δ / π")
ax.set_ylabel("归一化透射率")
ax.set_xlim(-2, 2)
ax.legend(fontsize=8)

# ------------------------------------------------- (c) F-P 透射谱
ax = axes[1, 0]
n, d = 1.0, 2e-3
lam = np.linspace(589.5e-9, 590.5e-9, 40000)
for r, c in [(0.5, "C0"), (0.8, "C1"), (0.95, "C2")]:
    T = itf.fabry_perot_transmission_wavelength(lam, n, d, r)
    ax.plot(lam * 1e9, T, color=c, lw=1, label=f"R={r**2:.2f}")
fsr = 590e-9 ** 2 / (2 * n * d)
ax.set_title(f"(c) F-P 透射谱（d=2 mm, FSR={fsr*1e12:.2f} pm）")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("透射率 T")
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 精细度与分辨本领
ax = axes[1, 1]
R = np.linspace(0.01, 0.999, 600)
r = np.sqrt(R)
ax.plot(R, itf.finesse(r), label="精细度 $F^*$")
m = 2 * d / 590e-9  # 干涉级次
ax.plot(R, itf.finesse(r) * m / 1e4, label=f"分辨本领 $mF^*/10^4$ (m={m:.0f})")
ax.set_yscale("log")
ax.set_title("(d) 精细度与分辨本领随反射率增长")
ax.set_xlabel("界面反射率 R")
ax.set_ylabel("数值（对数坐标）")
ax.legend(fontsize=8)

fig.suptitle("多光束干涉与法布里-珀罗干涉仪（第二章）", fontsize=13)
save_fig(fig, "d04_multibeam_fp.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
for R in (0.5, 0.8, 0.95, 0.99):
    r = np.sqrt(R)
    F = 4 * R / (1 - R) ** 2
    print(f"R={R:.2f}: F={F:8.1f}, 精细度 F*={itf.finesse(r):6.2f}, "
          f"Tm/TM = 1/(1+F) = {1/(1+F):.4f}")
print(f"\nF-P 干涉仪 d=2 mm, λ=590 nm:")
print(f"  干涉级次 m = 2d/λ = {2*d/590e-9:.0f}")
print(f"  自由光谱范围 FSR = λ²/(2d) = {590e-9**2/(2*d)*1e12:.3f} pm")
w = itf.fabry_perot_peak_width(590e-9, 1.0, d, 0.9)
print(f"  R=0.81 时透射峰半宽 Δλ = {w*1e15:.4f} fm, 分辨本领 λ/Δλ = {590e-9/w:.3e}")
print("\n考点提醒：条纹“细锐”来自多光束叠加，不是单缝衍射；")
print("          双光束条纹是 cos² 型，多光束条纹是洛伦兹型尖峰。")

# -*- coding: utf-8 -*-
"""实验 03：双光束干涉 —— 杨氏双缝、条纹间距、可见度。

对应考点（第二章）：
    1. 干涉条件与光程差 Delta = d sin(theta)
    2. 条纹间距 Dx = lambda D / d（D 为缝屏距离）
    3. 单缝衍射包络对条纹的调制（双缝的“缺级”）
    4. 条纹可见度 V = (Imax - Imin)/(Imax + Imin)
运行：  python demos/d03_two_beam.py
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

lam = 600e-9
z = 1.0
x = np.linspace(-6e-3, 6e-3, 4000)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ---------------------------------------------------- (a) 纯干涉 vs 含包络
ax = axes[0, 0]
ax.plot(x * 1e3, itf.double_slit_intensity(x, lam, 0.5e-3, z=z),
        lw=0.8, label="仅干涉因子 $\\cos^2$")
ax.plot(x * 1e3, itf.double_slit_intensity(x, lam, 0.5e-3, a=0.1e-3, z=z),
        lw=1.2, label="干涉 × 单缝衍射包络 (a=0.1 mm)")
d = 0.5e-3
for m in range(1, 4):
    ax.axvline(m * lam * z / d * 1e3, color="gray", ls=":", lw=0.6)
ax.set_title("(a) 杨氏双缝：干涉因子 × 衍射因子 (d=0.5 mm)")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-4, 4)
ax.legend(fontsize=8)

# ---------------------------------------------------- (b) 缝间距的影响
ax = axes[0, 1]
for dd, c in [(0.2e-3, "C0"), (0.5e-3, "C1"), (1.0e-3, "C2")]:
    ax.plot(x * 1e3, itf.double_slit_intensity(x, lam, dd, z=z), color=c,
            label=f"d={dd*1e3:.1f} mm, Δx={itf.fringe_spacing(lam, dd, z)*1e3:.2f} mm")
ax.set_title("(b) 条纹间距与缝间距成反比")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(-3, 3)
ax.legend(fontsize=8)

# ---------------------------------------------------- (c) 波长的影响
ax = axes[1, 0]
wls = [400e-9, 500e-9, 600e-9, 700e-9]
colors = plt.cm.rainbow(np.linspace(0, 0.9, len(wls)))
for w, c in zip(wls, colors):
    ax.plot(x * 1e3, itf.double_slit_intensity(x, w, 0.5e-3, z=z) + 0.0,
            color=c, label=f"λ={w*1e9:.0f} nm")
ax.set_title("(c) 条纹间距与波长成正比")
ax.set_xlabel("屏上坐标 x / mm")
ax.set_ylabel("相对强度")
ax.set_xlim(0, 6)
ax.legend(fontsize=8)

# ---------------------------------------------------- (d) 可见度与光源
ax = axes[1, 1]
I1 = np.linspace(0.01, 1.0, 300)
ax.plot(I1, itf.visibility_two_sources(I1, 1.0))
ax.axhline(1.0, color="gray", ls=":", lw=0.8)
ax.text(0.05, 1.02, "等强度时 V=1", fontsize=8, color="gray")
ax.set_title("(d) 两光束强度比对条纹可见度的影响")
ax.set_xlabel("$I_1/I_2$（设 $I_2$ 不变）")
ax.set_ylabel("可见度 V")
ax.set_ylim(0, 1.1)

fig.suptitle("双光束干涉（第二章）", fontsize=13)
save_fig(fig, "d03_two_beam.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
for dd in (0.2e-3, 0.5e-3, 1.0e-3):
    print(f"d = {dd*1e3:.1f} mm 时条纹间距 Δx = λD/d = "
          f"{itf.fringe_spacing(lam, dd, z)*1e3:.3f} mm")
print(f"相干长度（Δλ=0.1 nm, λ=600 nm）L_c = λ²/Δλ = "
      f"{itf.coherence_length(600e-9, 0.1e-9)*1e3:.1f} mm")
print(f"相干时间 τ_c = {itf.coherence_time(600e-9, 0.1e-9)*1e12:.3f} ps")
print("考点提醒：若题目给的是“第 m 级明纹位置”，先写光程差 Δ = d sinθ ≈ d x/D，")
print("          再令 Δ = mλ；千万不要忘记 θ 是小角近似成立的前提（x ≪ D）。")

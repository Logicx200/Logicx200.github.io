# -*- coding: utf-8 -*-
"""实验 06：典型干涉仪 —— 牛顿环、迈克尔逊干涉仪、等厚干涉。

对应考点（第二章第 4 节）：
    1. 牛顿环：r_暗 = √(mλR)，中心暗斑（反射光有半波损失）
    2. 迈克尔逊等倾干涉圆环：Δ = 2d cosθ，d 每变 λ/2 条纹移动一条
    3. 劈尖等厚干涉：条纹间距 Δx = λ/(2nα)
    4. 白光干涉的彩色条纹（零级为白色）
运行：  python demos/d06_interferometers.py
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
fig = plt.figure(figsize=(12, 8.6))
gs = fig.add_gridspec(2, 3)

# ------------------------------------------------- (a) 牛顿环二维图样
r = np.linspace(-3e-3, 3e-3, 800)
Rc = 2.0
rr = np.hypot(*np.meshgrid(r, r))
I2d = itf.newton_rings_intensity(rr, lam, Rc)
ax = fig.add_subplot(gs[0, 0])
im = ax.imshow(I2d, extent=[-3, 3, -3, 3], cmap="inferno", origin="lower")
ax.set_title("(a) 牛顿环（反射光，中心暗）")
ax.set_xlabel("x / mm")
ax.set_ylabel("y / mm")
plt.colorbar(im, ax=ax, fraction=0.046, label="相对强度")

# ------------------------------------------------- (b) 牛顿环径向强度与暗环半径
ax = fig.add_subplot(gs[0, 1])
r1 = np.linspace(0, 3e-3, 3000)
ax.plot(r1 * 1e3, itf.newton_rings_intensity(r1, lam, Rc), lw=1)
for m in range(1, 6):
    ax.axvline(itf.newton_dark_radius(m, lam, Rc) * 1e3, color="r", ls=":", lw=0.7)
ax.set_title("(b) 径向强度；红虚线为 $r_m=\\sqrt{m\\lambda R}$")
ax.set_xlabel("半径 r / mm")
ax.set_ylabel("相对强度")

# ------------------------------------------------- (c) r_m² 与 m 的线性关系
ax = fig.add_subplot(gs[0, 2])
m = np.arange(1, 11)
ax.plot(m, itf.newton_dark_radius(m, lam, Rc) ** 2 * 1e6, "o-",
        label="仿真暗环 $r_m^2$")
ax.plot(m, m * lam * Rc * 1e6, "r--", label="理论 $m\\lambda R$")
ax.set_title("(c) $r_m^2$ 与 m 成正比（测曲率半径的原理）")
ax.set_xlabel("暗环级次 m")
ax.set_ylabel("$r_m^2$ / mm²")
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 迈克尔逊等倾圆环
d = 0.25e-3
f_lens = 0.5
ax = fig.add_subplot(gs[1, 0])
xs = np.linspace(-25e-3, 25e-3, 700)
X, Y = np.meshgrid(xs, xs)
theta = np.hypot(X, Y) / f_lens
Im = itf.michelson_circular_intensity(theta, d, lam)
im = ax.imshow(Im, extent=[-25, 25, -25, 25], cmap="inferno", origin="lower")
ax.set_title(f"(d) 迈克尔逊等倾圆环（d={d*1e3:.2f} mm）")
ax.set_xlabel("屏上坐标 / mm")
plt.colorbar(im, ax=ax, fraction=0.046, label="相对强度")

# ------------------------------------------------- (e) d 变化时中心的明暗
ax = fig.add_subplot(gs[1, 1])
dd = np.linspace(0, 3 * lam, 1200)
ax.plot(dd / lam, itf.michelson_circular_intensity(0.0, dd, lam))
ax.set_title("(e) 中心强度随 d 周期变化（每条 $\\lambda/2$）")
ax.set_xlabel("镜面移动量 d / λ")
ax.set_ylabel("中心相对强度")

# ------------------------------------------------- (f) 劈尖等厚干涉（白光）
ax = fig.add_subplot(gs[1, 2])
alpha = 2e-4
xw = np.linspace(0, 6e-3, 2400)
wl = np.arange(400, 701, 5) * 1e-9
rgb = np.zeros((len(xw), 3))
for w in wl:
    I = 0.5 * (1 + np.cos(2 * np.pi * 2 * alpha * xw / w))
    # CIE 近似权重（用于示意彩色）
    wt = np.array([np.exp(-((w * 1e9 - 610) / 60) ** 2),
                   np.exp(-((w * 1e9 - 545) / 45) ** 2),
                   np.exp(-((w * 1e9 - 460) / 45) ** 2)])
    rgb += np.outer(I, wt)
rgb /= rgb.max()
ax.imshow(rgb[None, :, :], extent=[0, 6, 0, 1], aspect="auto", origin="lower")
ax.set_yticks([])
ax.set_title(f"(f) 劈尖白光等厚条纹（α={alpha*1e3:.2f} mrad）")
ax.set_xlabel("位置 x / mm")

fig.suptitle("典型干涉仪（第二章）", fontsize=13)
save_fig(fig, "d06_interferometers.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"牛顿环（λ=600 nm, R=2 m）:")
for m in (1, 3, 5):
    print(f"  第 {m} 暗环半径 r = {itf.newton_dark_radius(m, lam, Rc)*1e3:.3f} mm"
          f"；第 {m} 亮环半径 r = {itf.newton_bright_radius(m, lam, Rc)*1e3:.3f} mm")
print(f"  由 r_m² = mλR 得 R = r_m²/(mλ)，"
      f"m=5 时用仿真值算得 R = {itf.newton_dark_radius(5, lam, Rc)**2/(5*lam):.4f} m")
print(f"\n迈克尔逊干涉仪（λ=600 nm）：")
print(f"  d 每变化 λ/2 = {lam/2*1e9:.0f} nm，条纹移动一条")
print(f"  中心处相邻圆环角半径差 ≈ √(λ/d)：d={d*1e3:.2f} mm 时 "
      f"Δθ ≈ {np.degrees(np.sqrt(lam/d)):.3f}°")
print(f"\n劈尖（n=1, α=2×10⁻⁴ rad）条纹间距 Δx = λ/(2α) = "
      f"{itf.wedge_fringe_spacing(lam, alpha)*1e3:.3f} mm")
print("\n考点提醒：牛顿环反射光中心是暗斑（半波损失），透射光中心是亮斑；")
print("          迈克尔逊等倾圆环“越靠中心级次越高、环越疏”。")

# -*- coding: utf-8 -*-
"""实验 12：晶体光学 —— 双折射、波片、偏光干涉、电光与声光效应。

对应考点（第四、五章）：
    1. 单轴晶体的 o 光/e 光：n_e(θ)、正负晶体、走离角
    2. 波片：1/4 波片、1/2 波片厚度与相位延迟
    3. 晶体的偏光干涉：正交偏振器下 T = sin²2φ · sin²(δ/2)
    4. 线性电光效应（KDP 半波电压 V_π）与声光布喇格衍射
运行：  python demos/d12_crystal_optics.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import polarization as pol  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

no_c, ne_c = 1.6584, 1.4864   # 方解石（负晶体）
no_q, ne_q = 1.5443, 1.5534   # 石英（正晶体）
theta = np.linspace(0, np.pi / 2, 800)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 折射率角分布
ax = axes[0, 0]
ax.plot(np.degrees(theta), pol.extraordinary_index(no_c, ne_c, theta),
        label=f"方解石 $n_e(\\theta)$ (no={no_c}, ne={ne_c})")
ax.axhline(no_c, color="C0", ls="--", lw=0.8, label="方解石 $n_o$")
ax.plot(np.degrees(theta), pol.extraordinary_index(no_q, ne_q, theta), "C2",
        label="石英 $n_e(\\theta)$")
ax.axhline(no_q, color="C2", ls="--", lw=0.8, label="石英 $n_o$")
ax.annotate("沿光轴 θ=0：eo 不分", (5, 1.60), fontsize=8)
ax.set_title("(a) 单轴晶体折射率面截面：$1/n_e^2=\\cos^2\\theta/n_o^2+\\sin^2\\theta/n_e^2$")
ax.set_xlabel("波法线与光轴夹角 θ / (°)")
ax.set_ylabel("折射率")
ax.legend(fontsize=7)

# ------------------------------------------------- (b) 走离角
ax = axes[0, 1]
rho_c = np.degrees(np.abs(pol.walk_off_angle(no_c, ne_c, theta)))
rho_q = np.degrees(np.abs(pol.walk_off_angle(no_q, ne_q, theta)))
ax.plot(np.degrees(theta), rho_c, label="方解石（负晶体，最大 ≈6.2°）")
ax.plot(np.degrees(theta), rho_q, label="石英（正晶体，很小）")
ax.plot(np.degrees(theta[np.argmax(rho_c)]), rho_c.max(), "r*", ms=10)
ax.annotate(f"最大走离角 {rho_c.max():.2f}°\nθ={np.degrees(theta[np.argmax(rho_c)]):.1f}°",
            (np.degrees(theta[np.argmax(rho_c)]), rho_c.max()),
            textcoords="offset points", xytext=(10, -6), fontsize=8, color="r")
ax.set_title("(b) e 光走离角 vs 光轴夹角")
ax.set_xlabel("波法线与光轴夹角 θ / (°)")
ax.set_ylabel("走离角 ρ / (°)")
ax.legend(fontsize=8)

# ------------------------------------------------- (c) 波片与偏光干涉
ax = axes[1, 0]
lam = 589e-9
dn = abs(no_q - ne_q)
d_q = np.linspace(0, 4 * lam / (4 * dn), 800) * 1e6  # μm
delta = 2 * np.pi * dn * d_q * 1e-6 / lam
ax.plot(d_q, delta / np.pi, label="相位延迟 δ/π")
for kind, name, col in [("quarter", "1/4 波片", "C3"), ("half", "1/2 波片", "C1"),
                        ("full", "全波片", "C2")]:
    xx = pol.waveplate_thickness(lam, no_q, ne_q, kind) * 1e6
    ax.axvline(xx, color=col, ls="--", lw=1)
    ax.text(xx * 1.03, 1.0, f"{name}\n{xx:.1f} μm", fontsize=7, color=col)
ax.set_title("(c) 石英波片厚度与相位延迟（λ=589 nm）")
ax.set_xlabel("晶体厚度 d / μm")
ax.set_ylabel("相位延迟 δ / π")

ax = axes[1, 1]
d2 = np.linspace(0, 4 * np.pi, 800)
for phi, lab in [(np.pi / 4, "φ=45°"), (np.pi / 6, "φ=30°"),
                 (np.pi / 2, "φ=90°（无消光）")]:
    ax.plot(d2 / np.pi, pol.polarization_interference_transmission(d2, phi), label=lab)
ax.plot(d2 / np.pi, pol.polarization_interference_transmission(d2, np.pi / 4, "parallel"),
        "--", label="平行偏振器 φ=45°")
ax.set_title("(d) 偏光干涉：$T=\\sin^2 2\\varphi\\,\\sin^2(\\delta/2)$")
ax.set_xlabel("相位延迟 δ / π")
ax.set_ylabel("透射率 T")
ax.legend(fontsize=8)

fig.suptitle("晶体光学与感应双折射（第四、五章）", fontsize=13)
save_fig(fig, "d12_crystal_optics.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print("单轴晶体：")
print(f"  方解石 (no={no_c}, ne={ne_c}) 是负晶体：ne < no，"
      f"e 光最大走离角 {rho_c.max():.2f}°")
print(f"  石英   (no={no_q}, ne={ne_q}) 是正晶体：ne > no")
print(f"\n波片（石英，λ=589 nm，Δn={dn:.4f}）：")
for kind, name in [("quarter", "1/4 波片"), ("half", "1/2 波片"), ("full", "全波片")]:
    d = pol.waveplate_thickness(lam, no_q, ne_q, kind)
    print(f"  {name}: d = {d*1e6:8.2f} μm")
print(f"\n偏光干涉：正交偏振器 + 晶片")
print(f"  φ=45°、δ=π（半波片）时 T=1（最亮）；φ=0 或 90° 时 T≡0（永远消光）")
print(f"\nKDP 线性电光效应：")
Vpi = pol.pockels_half_wave_voltage(550e-9, 1.512, 10.6e-12)
print(f"  纵向半波电压 V_π = λ/(2 n_o³ r_63) = {Vpi/1e3:.2f} kV")
print(f"  δ = π·V/V_π，所以加 {Vpi/2/1e3:.2f} kV 得到 1/4 波片效果")
print(f"\n声光布喇格衍射（λ=633 nm, v=4000 m/s）：")
for fac in (40e6, 80e6, 120e6):
    thB = pol.acousto_optic_bragg_angle(633e-9, 4000.0, fac)
    print(f"  声频 {fac/1e6:5.0f} MHz (Λ={4000/fac*1e6:5.1f} μm): "
          f"θ_B = {thB*1e3:.4f} mrad = {np.degrees(thB)*1e3:.3f}×10⁻³ 度")
print("\n考点提醒：波片只改变偏振态、不改变光强（理想情况）；")
print("          正交偏振器 + 波片才会把“相位延迟”变成“强度变化”，这是所有")
print("          电光/声光调制器、偏光干涉仪的共同的原理骨架。")

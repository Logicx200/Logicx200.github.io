# -*- coding: utf-8 -*-
"""实验 02：偏振态的琼斯矩阵描述 —— 马吕斯定律、波片、偏振光合成。

对应考点（第一章 光波的偏振态 + 第四章 波片）：
    1. 用琼斯矢量表示线偏振、圆偏振、椭圆偏振
    2. 马吕斯定律 I = I0 cos^2(theta)
    3. 1/4 波片把线偏振变成椭圆/圆偏振的完整过程
    4. 正交偏振器 + 晶片（偏光干涉）的透射规律
运行：  python demos/d02_polarization_jones.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import polarization as pol  # noqa: E402
from optics817 import wave  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

fig = plt.figure(figsize=(12, 8.4))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1])

# ---------------------------------------------------------------- (a) 马吕斯
ax = fig.add_subplot(gs[0, 0])
a = np.linspace(0, 2 * np.pi, 720)
ax.plot(np.degrees(a), wave.malus(1.0, a))
ax.axvline(45, color="r", ls=":", lw=1)
ax.axvline(135, color="r", ls=":", lw=1)
ax.set_title("(a) 马吕斯定律 $I=I_0\\cos^2\\theta$")
ax.set_xlabel("检偏器与偏振方向夹角 θ / (°)")
ax.set_ylabel("相对强度 I/I0")
ax.set_xticks(range(0, 361, 45))

# ------------------------------------------------- (b) 线偏振器级联
ax = fig.add_subplot(gs[0, 1])
ang = np.linspace(0, 90, 400)
I = np.array([np.abs(wave.jones_linear_polarizer(np.radians(t))
                    @ wave.jones_linear_polarizer(np.radians(45))
                    @ wave.jones_linear(0.0)) ** 2
              for t in ang]).sum(axis=1)
ax.plot(ang, np.cos(np.radians(ang - 45)) ** 2 * np.cos(np.radians(45)) ** 2,
        label=r"解析值 $\cos^2 45°\cos^2(\theta-45°)$")
ax.plot(ang[::20], I[::20], "o", ms=4, label="琼斯矩阵数值")
ax.axvline(45, color="r", ls=":", lw=1)
ax.set_title("(b) 0° 偏振 → 45° 偏振片 → θ 偏振片")
ax.set_xlabel("第三片偏振片方向 θ / (°)")
ax.set_ylabel("透射强度")
ax.legend(fontsize=8)

# ------------------------------------------- (c) 偏振态的李萨如轨迹
ax = fig.add_subplot(gs[0, 2])
for delta, lab in [(0, "δ=0 线偏振"), (np.pi / 2, "δ=π/2 圆偏振"),
                   (np.pi, "δ=π 线偏振(转90°)"), (np.pi / 3, "δ=π/3 椭圆")]:
    J = wave.jones_waveplate(delta, 0.0) @ wave.jones_linear(np.pi / 4)
    t = np.linspace(0, 2 * np.pi, 400)
    E = np.real(J[:, None] * np.exp(-1j * t))
    ax.plot(E[0], E[1], label=lab)
ax.set_aspect("equal")
ax.set_title("(c) 45° 线偏振经波片后的偏振态")
ax.set_xlabel("$E_x$")
ax.set_ylabel("$E_y$")
ax.legend(fontsize=7, loc="upper right", framealpha=0.9)

# ------------------------------------------- (d) 波片延迟量扫描
ax = fig.add_subplot(gs[1, 0])
dl = np.linspace(0, 2 * np.pi, 600)
J0 = wave.jones_linear(np.pi / 4)
S3 = np.array([wave.stokes_from_jones(wave.jones_waveplate(d, 0.0) @ J0)[3]
               for d in dl])
ax.plot(np.degrees(dl), S3)
for d, name in [(np.pi / 2, "1/4 波片"), (np.pi, "1/2 波片")]:
    ax.axvline(np.degrees(d), color="r", ls=":", lw=1)
    ax.text(np.degrees(d) + 3, 0.55, name, color="r", fontsize=9)
ax.set_title("(d) 偏振态随波片相位延迟的变化")
ax.set_xlabel("相位延迟 δ / (°)")
ax.set_ylabel("归一化 $S_3/S_0$（圆偏振度）")

# ------------------------------------------- (e) 偏光干涉
ax = fig.add_subplot(gs[1, 1])
d2 = np.linspace(0, 4 * np.pi, 800)
for phi, lab in [(np.pi / 4, "φ=45°"), (np.pi / 8, "φ=22.5°"),
                 (np.pi / 2, "φ=90°")]:
    ax.plot(d2 / np.pi, pol.polarization_interference_transmission(d2, phi), label=lab)
ax.set_title("(e) 正交偏振器间的晶片（偏光干涉）")
ax.set_xlabel("相位延迟 δ / π")
ax.set_ylabel("透射率 T")
ax.legend(fontsize=8)

# ------------------------------------------- (f) 波片厚度设计
ax = fig.add_subplot(gs[1, 2])
no, ne = 1.5443, 1.5534  # 石英
lam = np.linspace(400e-9, 700e-9, 200)
ax.plot(lam * 1e9, pol.waveplate_thickness(lam, no, ne, "quarter") * 1e6,
        label="1/4 波片厚度")
ax.plot(lam * 1e9, pol.waveplate_thickness(lam, no, ne, "half") * 1e6,
        label="1/2 波片厚度")
ax.axvline(589, color="r", ls=":", lw=1)
ax.text(592, 20, "589 nm", color="r", fontsize=8)
ax.set_title("(f) 石英波片厚度与波长的关系")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("厚度 d / μm")
ax.legend(fontsize=8)

fig.suptitle("偏振光与琼斯矩阵（第一、四章）", fontsize=13)
save_fig(fig, "d02_polarization_jones.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
Jq = wave.jones_waveplate(np.pi / 2, 0.0) @ wave.jones_linear(np.pi / 4)
psi, chi, hand = wave.polarization_ellipse(Jq)
print(f"45° 线偏振经过 1/4 波片 → {hand}圆偏振（方位角 ψ={np.degrees(psi):.2f}°, "
      f"椭率角 χ={np.degrees(chi):.2f}°）")
print(f"石英 1/4 波片（λ=589 nm）厚度 d = "
      f"{pol.waveplate_thickness(589e-9, no, ne, 'quarter') * 1e6:.2f} μm")
I3 = np.sum(np.abs(wave.jones_linear_polarizer(np.pi / 2)
                   @ wave.jones_linear_polarizer(np.pi / 4)
                   @ wave.jones_linear(0.0)) ** 2)
print(f"线偏振依次通过 45°、90° 偏振片后强度 = {I3:.4f}（相对 0° 偏振光，即 1/4）")
print("若入射为自然光，则再乘 1/2 → 1/8，这就是经典的“三片偏振片”结论。")
print("提醒：把 45° 偏振片抽掉，0° 与 90° 正交时透射为 0；"
      "插入后反而有光 —— 偏振片不是简单“滤光”，它改变了偏振态。")

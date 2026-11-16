# -*- coding: utf-8 -*-
"""实验 01：菲涅耳公式 —— 反射率、布儒斯特角、全反射与相移。

对应考点（第一章）：
    1. 反射定律、折射定律、菲涅耳公式的四种形式
    2. 反射率随入射角的变化；自然光反射的偏振化
    3. 布儒斯特角 tan(i_B) = n2/n1，此时 r_p = 0
    4. 全反射临界角 sin(i_C) = n2/n1 与全反射相移
运行：  python demos/d01_fresnel.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import wave  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

n1, n2 = 1.0, 1.5
th = np.linspace(0.0, np.pi / 2 * 0.999, 3000)
f_air2glass = wave.fresnel(n1, n2, th)
f_glass2air = wave.fresnel(n2, n1, th)
thB = wave.brewster_angle(n1, n2)
thC = wave.critical_angle(n2, n1)
ds, dp = wave.tir_phase_shifts(n2, n1, th)

fig, axes = plt.subplots(2, 2, figsize=(11, 8))

ax = axes[0, 0]
ax.plot(np.degrees(th), f_air2glass["Rs"], label=r"$R_s$（垂直纸面振动）")
ax.plot(np.degrees(th), f_air2glass["Rp"], label=r"$R_p$（平行纸面振动）")
ax.plot(np.degrees(th), 0.5 * (f_air2glass["Rs"] + f_air2glass["Rp"]),
        "--", label="自然光反射率")
ax.axvline(np.degrees(thB), color="k", lw=1, ls=":")
ax.annotate(f"布儒斯特角\n{np.degrees(thB):.2f}°", (np.degrees(thB), 0.5),
            xytext=(np.degrees(thB) - 45, 0.62),
            arrowprops=dict(arrowstyle="->", lw=0.8))
ax.set_title("(a) 空气 → 玻璃 (n=1.5)：反射率随入射角")
ax.set_xlabel("入射角 i / (°)")
ax.set_ylabel("反射率 R")
ax.legend(fontsize=8)
ax.set_ylim(0, 1)

ax = axes[0, 1]
ax.plot(np.degrees(th), f_glass2air["Rs"], label=r"$R_s$")
ax.plot(np.degrees(th), f_glass2air["Rp"], label=r"$R_p$")
ax.axvline(np.degrees(thC), color="r", lw=1, ls=":")
ax.axvspan(np.degrees(thC), 90, color="r", alpha=0.08)
ax.text(np.degrees(thC) + 2, 0.45, "全反射区\nR ≡ 1", color="r", fontsize=9)
ax.set_title(f"(b) 玻璃 → 空气：临界角 {np.degrees(thC):.2f}°")
ax.set_xlabel("入射角 i / (°)")
ax.set_ylabel("反射率 R")
ax.legend(fontsize=8)
ax.set_ylim(0, 1.05)

ax = axes[1, 0]
mask = th > thC
ax.plot(np.degrees(th[mask]), np.degrees(ds[mask]), label=r"$\delta_s$")
ax.plot(np.degrees(th[mask]), np.degrees(dp[mask]), label=r"$\delta_p$")
ax.plot(np.degrees(th[mask]), np.degrees(dp[mask] - ds[mask]), "--",
        label=r"$\delta_p-\delta_s$（相位延迟）")
ax.axvline(np.degrees(thC), color="r", lw=1, ls=":")
ax.set_title("(c) 全反射相移（玻璃 → 空气）")
ax.set_xlabel("入射角 i / (°)")
ax.set_ylabel("相移 / (°)")
ax.legend(fontsize=8)

ax = axes[1, 1]
sub = th < thC
ph_s = np.degrees(np.angle(f_glass2air["rs"][sub]))
ph_p = np.degrees(np.angle(f_glass2air["rp"][sub]))
ax.plot(np.degrees(th[sub]), ph_s, label=r"$\arg r_s$")
ax.plot(np.degrees(th[sub]), ph_p, label=r"$\arg r_p$")
ax.axhline(180, color="gray", lw=0.8, ls=":")
ax.text(1.5, 145, "π 相位跃变（半波损失）", fontsize=8, color="gray")
ax.text(35, 40, "布儒斯特角处\n$r_p$ 相位反转 180°", fontsize=8, color="C1")
ax.set_title("(d) 部分反射区的相位：光疏→光密有 π 跃变")
ax.set_xlabel("入射角 i / (°)")
ax.set_ylabel("相位 / (°)")
ax.set_ylim(-10, 200)
ax.legend(fontsize=8, loc="center right")

fig.suptitle("菲涅耳公式：反射率与相位（第一章）", fontsize=13)
save_fig(fig, "d01_fresnel.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"正入射（空气→玻璃 n=1.5）反射率 R = {f_air2glass['Rs'][0]:.4f}"
      f"  （单面 4%，双面约 8%）")
print(f"布儒斯特角 i_B = {np.degrees(thB):.3f}°，此时 R_p = "
      f"{wave.fresnel(n1, n2, thB)['Rp']:.2e}")
print(f"全反射临界角 i_C = {np.degrees(thC):.3f}°（玻璃→空气）")
print(f"全反射最大相位差 (δp-δs) = {np.degrees((dp - ds)[mask].max()):.2f}°"
      f"  —— 菲涅耳菱体制造圆偏振的依据")
print(f"自然光以布儒斯特角入射时，反射光偏振度 = "
      f"{(f_air2glass['Rs'][np.argmin(abs(th - thB))] - 0) / f_air2glass['Rs'][np.argmin(abs(th - thB))]:.3f}")

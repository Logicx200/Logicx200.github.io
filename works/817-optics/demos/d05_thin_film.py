# -*- coding: utf-8 -*-
"""实验 05：光学薄膜 —— 增透膜、高反膜、干涉滤光片。

对应考点（第二章第 3 节）：
    1. 单层 1/4 波长增透膜：n = sqrt(n0 ns) 时 R = 0，d = λ0/(4n)
    2. 膜厚/波长偏离 λ0 时增透效果的退化
    3. 多层高反膜：反射率随层数迅速上升（特征矩阵法）
    4. 干涉滤光片的选频特性
运行：  python demos/d05_thin_film.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import interference as itf  # noqa: E402
from optics817 import wave  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

lam0 = 550e-9
n0, ns = 1.0, 1.52
lam = np.linspace(400e-9, 750e-9, 900)

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

# ------------------------------------------------- (a) 单层增透膜
ax = axes[0, 0]
for nf, c in [(1.0, "gray"), (1.22, "C0"), (np.sqrt(n0 * ns), "C3"), (1.7, "C1")]:
    d = lam0 / (4 * nf)
    R = itf.thin_film_reflectance(lam, n0, nf, ns, d)
    ax.plot(lam * 1e9, R * 100, color=c,
            label=f"n={nf:.3f}（d={d*1e9:.0f} nm）")
ax.axvline(lam0 * 1e9, color="k", ls=":", lw=0.8)
ax.text(lam0 * 1e9 + 4, 3.6, "设计波长 550 nm", fontsize=8)
ax.set_title("(a) 单层 1/4 波长增透膜：$n=\\sqrt{n_0n_s}$ 时 R=0")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("反射率 R / %")
ax.legend(fontsize=8)

# ------------------------------------------------- (b) 膜厚偏离
ax = axes[0, 1]
nf = np.sqrt(n0 * ns)
for dd, c in [(lam0 / (4 * nf), "C2"), (lam0 / (2 * nf), "C1"),
              (lam0 / (8 * nf), "C0"), (3 * lam0 / (4 * nf), "C3")]:
    R = itf.thin_film_reflectance(lam, n0, nf, ns, dd)
    ax.plot(lam * 1e9, R * 100, color=c, label=f"d = {dd/(lam0/nf):.3f} λ/n")
ax.set_title("(b) 膜厚偏离 1/4 波长时反射率上升")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("反射率 R / %")
ax.legend(fontsize=8)

# ------------------------------------------------- (c) 多层高反膜
ax = axes[1, 0]
nH, nL = 2.30, 1.38  # ZnS / MgF2
for pairs, c in [(2, "C0"), (4, "C1"), (8, "C2"), (12, "C3")]:
    n_list, d_list = [n0], []
    for _ in range(pairs):
        n_list += [nH, nL]
        d_list += [lam0 / (4 * nH), lam0 / (4 * nL)]
    n_list += [ns]
    R = np.array([wave.reflectance_multilayer_normal(n_list, d_list, l) for l in lam])
    ax.plot(lam * 1e9, R * 100, color=c, label=f"{2*pairs} 层（{pairs} 对 H/L）")
ax.axvline(lam0 * 1e9, color="k", ls=":", lw=0.8)
ax.set_title("(c) 多层高反膜：层数越多反射率越高")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("反射率 R / %")
ax.legend(fontsize=8)

# ------------------------------------------------- (d) 干涉滤光片
ax = axes[1, 1]
# 结构：H L H L | 2L 腔 | L H L H  (H: 高折射率, L: 低折射率)
spacer = lam0 / (2 * nL)
n_list, d_list = [n0], []
for _ in range(3):
    n_list += [nH, nL]
    d_list += [lam0 / (4 * nH), lam0 / (4 * nL)]
n_list += [nL]
d_list += [spacer]
for _ in range(3):
    n_list += [nL, nH]
    d_list += [lam0 / (4 * nL), lam0 / (4 * nH)]
n_list += [ns]
for extra, c in [(0.0, "C0"), (0.05, "C1"), (0.12, "C2")]:
    n2 = list(n_list)
    dd = list(d_list)
    dd[6] = spacer * (1 + extra)          # 改变腔厚，中心波长移动
    R = np.array([wave.reflectance_multilayer_normal(n2, dd, l) for l in lam])
    ax.plot(lam * 1e9, (1 - R) * 100, color=c,
            label=f"腔厚 ×{1+extra:.2f}")
ax.set_title("(d) 干涉滤光片透射谱（腔厚决定中心波长）")
ax.set_xlabel("波长 λ / nm")
ax.set_ylabel("透射率 T / %")
ax.legend(fontsize=8)

fig.suptitle("光学薄膜（第二章）", fontsize=13)
save_fig(fig, "d05_thin_film.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"玻璃基底 n_s={ns}：理想增透膜折射率 n = sqrt(1.52) = {np.sqrt(ns):.4f}")
print(f"  找不到这个材料的常用替代：MgF2 (1.38) → 单面 R = "
      f"{wave.quarter_wave_reflectance(n0, 1.38, ns)*100:.2f}%")
print(f"  1/4 波长膜几何厚度 d = λ0/(4n)（λ0=550 nm, n=1.23） = "
      f"{lam0/(4*np.sqrt(ns))*1e9:.1f} nm")
print(f"\n多层高反膜（λ0=550 nm, H=ZnS 2.30 / L=MgF2 1.38, 基底 n=1.52）：")
for pairs in (2, 4, 8, 12):
    n_list, d_list = [n0], []
    for _ in range(pairs):
        n_list += [nH, nL]
        d_list += [lam0 / (4 * nH), lam0 / (4 * nL)]
    n_list += [ns]
    R = wave.reflectance_multilayer_normal(n_list, d_list, lam0)
    print(f"  {2*pairs:2d} 层: R = {R*100:6.2f}%")
print("\n考点提醒：单层膜公式 R = [(n0ns - n²)/(n0ns + n²)]² 只对 1/4 波长膜成立；")
print("          膜厚偏差、入射角变化、波长偏离都会让 R 迅速上升。")

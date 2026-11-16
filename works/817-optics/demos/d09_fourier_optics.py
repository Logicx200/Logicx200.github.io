# -*- coding: utf-8 -*-
"""实验 09：傅里叶光学 —— 阿贝成像、4f 空间滤波、传递函数。

对应考点（第三章第 5 节）：
    1. 透镜的傅里叶变换性质：后焦面上的光场是物函数的频谱
    2. 阿贝成像原理：成像 = 干涉级次的重组
    3. 空间滤波：低通（去细节）、高通（勾边）
    4. 相干传递函数 CTF 与光学传递函数 OTF 的截止频率差别
运行：  python demos/d09_fourier_optics.py
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from optics817 import fourier_optics as fo  # noqa: E402
from optics817.plotstyle import save_fig  # noqa: E402

lam = 600e-9
N, dx, f = 1024, 2e-6, 0.3

# 物：一组不同周期条纹 + 一个方孔（模拟“有细节的物体”）
X, Y, x = fo.grid(N, dx)
obj = np.zeros((N, N))
mask_band = (np.abs(X) < 0.3e-3) & (np.abs(Y) < 0.6e-3)
period = 32e-6
obj[mask_band] = 0.5 + 0.5 * np.cos(2 * np.pi * X[mask_band] / period)
obj[(np.abs(X - 0.6e-3) < 0.15e-3) & (np.abs(Y) < 0.15e-3)] = 1.0

U_f, dxf, xf = fo.lens_fourier(obj.astype(complex), lam, f, dx)
I_spec = np.abs(U_f) ** 2

# ------------------------------------------------- 三种滤波器
fx = xf / (lam * f)  # 空间频率坐标
FX, FY = np.meshgrid(fx, fx)
r_freq = np.hypot(FX, FY)
mask_lp = (r_freq < 1.2e4).astype(complex)                 # 低通
mask_hp = (r_freq > 1.2e4).astype(complex)                 # 高通
mask_abbe = (np.abs(FY) < 0.6e4).astype(complex) * (np.abs(FX) < 1.0e4)  # 只留低横向频率

results = {}
for name, m in [("原物", None), ("低通", mask_lp), ("高通", mask_hp), ("阿贝选频", mask_abbe)]:
    if m is None:
        Ui = fo.four_f_system(obj.astype(complex), lam, f, dx, None)[0]
    else:
        Ui = fo.four_f_system(obj.astype(complex), lam, f, dx, m)[0]
    results[name] = np.abs(Ui) ** 2

fig = plt.figure(figsize=(13, 8))
gs = fig.add_gridspec(2, 4)

for i, (name, img) in enumerate(results.items()):
    ax = fig.add_subplot(gs[0, i])
    ax.imshow(img, extent=[x[0] * 1e3, x[-1] * 1e3, x[0] * 1e3, x[-1] * 1e3],
              cmap="gray", origin="lower")
    ax.set_title(f"(a{i+1}) {name}", fontsize=10)
    ax.set_xlabel("x / mm", fontsize=8)
    ax.tick_params(labelsize=7)

ax = fig.add_subplot(gs[1, 0:2])
ax.imshow(np.log1p(I_spec), extent=[xf[0] * 1e3, xf[-1] * 1e3, xf[0] * 1e3, xf[-1] * 1e3],
          cmap="inferno", origin="lower")
ax.set_title("(b) 谱面（后焦面）强度 $\\log(1+|U|^2)$：中心为低频")
ax.set_xlabel("谱面坐标 / mm")
ax.set_ylabel("谱面坐标 / mm")

ax = fig.add_subplot(gs[1, 2])
fc_ctf = 2e-3 / (2 * lam * f)
ff = np.linspace(-3 * fc_ctf, 3 * fc_ctf, 800)
ax.plot(ff, fo.ctf_circular(ff, 0, lam, 2e-3, f), label="CTF（相干）")
ax.plot(ff, fo.otf_circular(ff, fc_ctf), label="OTF（非相干）")
ax.axvline(fc_ctf, color="gray", ls=":", lw=0.8)
ax.axvline(2 * fc_ctf, color="gray", ls="--", lw=0.8)
ax.text(fc_ctf * 1.05, 0.55, "$f_c$", fontsize=9)
ax.text(2 * fc_ctf * 1.02, 0.25, "$2f_c$", fontsize=9)
ax.set_title("(c) 传递函数：OTF 截止频率是 CTF 的 2 倍")
ax.set_xlabel("空间频率 f / (1/m)")
ax.set_ylabel("归一化响应")
ax.legend(fontsize=8)

ax = fig.add_subplot(gs[1, 3])
U_rec, _, _ = fo.lens_fourier(U_f, lam, f, dxf)   # 再变换一次 = 倒像
ax.plot(x * 1e3, obj[N // 2] / obj.max(), "C0", lw=0.8, label="物（中心行）")
ax.plot(x * 1e3, np.abs(U_rec[N // 2]) / np.abs(U_rec).max(), "C1", lw=0.8,
        label="4f 成像（无滤波）")
ax.set_xlim(-1.2, 1.2)
ax.set_title("(d) 两次傅里叶变换给出倒像")
ax.set_xlabel("x / mm")
ax.legend(fontsize=7)

fig.suptitle("傅里叶光学与空间滤波（第三章第 5 节）", fontsize=13)
save_fig(fig, "d09_fourier_optics.png")

print("=" * 66)
print("关键结果")
print("=" * 66)
print(f"透镜焦距 f={f*1000:.0f} mm，物面采样 dx={dx*1e6:.0f} μm，N={N}")
print(f"  谱面采样间隔 dx_f = λf/(N dx) = {dxf*1e6:.3f} μm")
print(f"  物面空间频率上限（由采样决定）= 1/(2dx) = {1/(2*dx):.3e} /m")
print(f"  圆孔直径 D=2 mm 时：CTF 截止频率 fc = D/(2λf) = {2e-3/(2*lam*f):.3e} /m")
print(f"                      OTF 截止频率 2fc = {2*2e-3/(2*lam*f):.3e} /m")
print(f"  对应物面可分辨的最小周期：相干 1/fc = {1/(2e-3/(2*lam*f))*1e6:.2f} μm，"
      f"非相干 1/(2fc) = {1/(2*2e-3/(2*lam*f))*1e6:.2f} μm")
print("\n记忆要点：")
print("  * 相干照明看 CTF（振幅响应，0/1 截止），非相干照明看 OTF（强度响应）")
print("  * 阿贝成像：让更多衍射级次通过 → 像更接近物；挡住级次 → 细节消失")
print("  * 低通滤波 = 模糊；高通滤波 = 勾边（边缘增强）")

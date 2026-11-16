# -*- coding: utf-8 -*-
"""收集报告所需的定量数据 (控制变量扫描、WKB 精度、数值验证汇总)."""
import numpy as np
from tunneling_core import t_exact, t_wkb, t_wkb_simple

np.set_printoptions(suppress=True)
print("=" * 96)
print("[A] 控制变量扫描: 透射概率 T (势垒高度 V0 / 宽度 a / 能量 E)")
print("=" * 96)

print("\nA1. 固定 a=1, 改变 V0 (行=V0, 列=E):")
Es = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
V0s = [0.5, 1.0, 2.0, 3.0, 5.0, 8.0]
print(f"{'V0/E':>7}" + "".join(f"{e:>12}" for e in Es))
for V0 in V0s:
    print(f"{V0:>7}" + "".join(f"{float(t_exact(e,V0,1.0)):>12.4e}" for e in Es))

print("\nA2. 固定 V0=2, 改变 a (行=a, 列=E):")
as_ = [0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0]
print(f"{'a/E':>7}" + "".join(f"{e:>12}" for e in Es))
for a in as_:
    print(f"{a:>7}" + "".join(f"{float(t_exact(e,2.0,a)):>12.4e}" for e in Es))

print("\nA3. 固定 E=0.5, 改变 (V0, a) -> T:")
a_s = [0.25, 0.5, 1.0, 2.0, 3.0]
print(f"{'V0/a':>7}" + "".join(f"{a:>12}" for a in a_s))
for V0 in V0s:
    print(f"{V0:>7}" + "".join(f"{float(t_exact(0.5,V0,a)):>12.4e}" for a in a_s))

print("\nA4. 隧穿区指数律: ln T 对 a 的斜率 (V0=2, E=0.5, 理论 -2*kappa)")
for E in [0.25, 0.5, 1.0, 1.5]:
    aa = np.linspace(0.05, 6.0, 400)
    lnT = np.log(t_exact(E, 2.0, aa))
    k = np.polyfit(aa, lnT, 1)[0]
    kappa = np.sqrt(2.0 * (2.0 - E))
    print(f"  E={E:4}: 拟合斜率={k:9.4f}   理论 -2*kappa={-2*kappa:9.4f}   相对差={abs(k+2*kappa)/2/kappa*100:5.2f}%")

print("\nA5. 隧穿区指数律: ln T 对 sqrt(2m(V0-E)) 的斜率 (a=1, 理论 -2a=-2)")
for V0 in [2.0, 5.0, 8.0]:
    E2 = np.linspace(0.02, V0 - 0.05, 400)
    x = np.sqrt(2.0 * (V0 - E2))
    k = np.polyfit(x, np.log(t_exact(E2, V0, 1.0)), 1)[0]
    print(f"  V0={V0:4}: 拟合斜率={k:9.4f}   理论 -2a=-2.0000   相对差={abs(k+2.0)/2*100:5.2f}%")

print()
print("=" * 96)
print("[B] WKB 近似精度 (比值 = T_WKB / T_exact)")
print("=" * 96)
print(f"{'V0':>5} {'a':>5} {'E':>7} {'kappa*a':>9} {'T_exact':>14} {'WKB':>14} {'WKB+前置':>14} {'WKB比':>8} {'简化比':>8}")
for V0, a in [(5.0, 2.0), (5.0, 6.0), (8.0, 3.0), (2.0, 1.0)]:
    for E in [0.1, 0.5, 1.0, 0.9 * V0]:
        te = float(t_exact(E, V0, a))
        tw = float(t_wkb(E, V0, a))
        ts = float(t_wkb_simple(E, V0, a))
        ka = np.sqrt(2.0 * max(V0 - E, 0.0)) * a
        print(f"{V0:5} {a:5} {E:7.3f} {ka:9.2f} {te:14.6e} {tw:14.6e} {ts:14.6e} "
              f"{tw/te:8.4f} {ts/te:8.4f}")

print()
print("=" * 96)
print("[C] 时域仿真的数值透射率 vs 解析值 (动画场景, 记录在 data/*.npz)")
print("=" * 96)
import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
print(f"{'场景':>18} {'V0':>5} {'a':>5} {'E0':>7} {'数值T':>12} {'解析T(E0)':>12} {'谱平均':>12} {'相对偏差':>9}")
for f in sorted(os.listdir(D)):
    if not f.endswith(".npz"):
        continue
    d = np.load(os.path.join(D, f))
    name = f.replace("_timeseries.npz", "")
    num, ex, sp = float(d["T_numeric"]), float(d["T_exact"]), float(d["T_spectral"])
    print(f"{name:>18} {float(d['V0']):5g} {float(d['a']):5g} {float(d['E0']):7.3f} "
          f"{num:12.6f} {ex:12.6f} {sp:12.6f} {abs(num-sp)/sp*100:8.3f}%")

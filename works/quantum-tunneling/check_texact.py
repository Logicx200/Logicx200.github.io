# -*- coding: utf-8 -*-
"""
校验 t_exact(向量化形式) 与逐点高精度实现一致, 覆盖大 kappa*a 的深隧穿极限.

逐点参考实现用 Python 复数运算直接套用标准公式, 不使用任何向量化技巧:
    隧穿区: T = 4E(V0-E) / (4E(V0-E) + V0^2 sinh^2(kappa a))
    越顶区: T = 1 / (1 + V0^2 sin^2(k2 a)/(4E(E-V0)))
"""
import numpy as np
from tunneling_core import t_exact


def t_ref_one(E, V0, a, m=1.0, hbar=1.0):
    if E <= 0:
        return 0.0
    if abs(E - V0) < 1e-12:
        return 1.0 / (1.0 + m * V0 * a ** 2 / (2.0 * hbar ** 2))
    if E < V0:
        kappa = np.sqrt(2.0 * m * (V0 - E)) / hbar
        sh = np.sinh(kappa * a)
        return 4.0 * E * (V0 - E) / (4.0 * E * (V0 - E) + V0 ** 2 * sh ** 2)
    k2 = np.sqrt(2.0 * m * (E - V0)) / hbar
    return 1.0 / (1.0 + V0 ** 2 * np.sin(k2 * a) ** 2 / (4.0 * E * (E - V0)))


print(f"{'V0':>6} {'a':>5} {'E':>8} {'kappa*a':>9} {'T_vec':>14} {'T_ref':>14} {'相对差':>10}")
worst = 0.0
worst_case = None
for V0, a in [(2.0, 1.0), (5.0, 1.0), (5.0, 2.0), (5.0, 6.0), (20.0, 5.0), (100.0, 10.0), (0.5, 1.0)]:
    for E in [0.02, 0.05, 0.2, 0.5, 1.0, 2.0, 4.999, 5.0, 5.001, 6.0, 20.0, 60.0]:
        tv = float(t_exact(E, V0, a))
        tr = float(t_ref_one(E, V0, a))
        kappa_a = np.sqrt(2.0 * max(V0 - E, 0.0)) * a
        if tr > 0:
            rel = abs(tv - tr) / tr
            if rel > worst:
                worst, worst_case = rel, (V0, a, E)
        print(f"{V0:6} {a:5} {E:8.3f} {kappa_a:9.2f} {tv:14.6e} {tr:14.6e} {rel:10.2e}")
print()
print("最大相对差 =", f"{worst:.3e}", " 出现于", worst_case)
# 极端深隧穿: 必须既不溢出也不为负
for V0, a, E in [(100.0, 10.0, 0.05), (1000.0, 100.0, 1.0), (5.0, 60.0, 0.5)]:
    tv = float(t_exact(E, V0, a))
    tr = float(t_ref_one(E, V0, a))
    print(f"  V0={V0} a={a} E={E}: T_vec={tv:.6e} T_ref={tr:.6e} 有限={np.isfinite(tv)}")

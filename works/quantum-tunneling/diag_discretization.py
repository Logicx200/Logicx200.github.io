# -*- coding: utf-8 -*-
"""离散化收敛性诊断: 点取样方势垒的边缘处理对数值透射率的影响."""
import numpy as np
from tunneling_core import (gaussian_packet, rect_barrier, split_operator_evolve,
                            spectrum_average_T, t_exact)


def smoothed_barrier(x, V0, a, w):
    """把方势垒边缘用宽度 w 的 cos^2 斜坡平滑 (w=0 即硬边缘)."""
    if w <= 0:
        return rect_barrier(x, V0, a)
    half = a / 2.0
    V = np.zeros_like(x)
    ax = np.abs(x)
    V[ax <= half - w / 2] = V0
    ramp = (ax > half - w / 2) & (ax < half + w / 2)
    V[ramp] = V0 * 0.5 * (1.0 - np.cos(np.pi * (half + w / 2 - ax[ramp]) / w))
    return V


L = 400.0
E0 = 0.5 * 1.8 ** 2
REF = 0.388126          # 连续极限下的谱平均 (见 selftest)
print(f"参考值: 谱平均 <T> = {REF:.6f}, T_exact(E0) = {t_exact(E0,2.0,1.0):.6f}")
print()
print(f"{'w/dx':>5} {'N':>7} {'dx':>9} {'T(数值)':>10} {'误差':>11}")
for fw in [0.0, 0.5, 1.0, 1.5, 2.0]:
    for N in [4096, 8192, 16384, 32768]:
        x = np.linspace(-L / 2, L / 2, N, endpoint=False)
        dx = x[1] - x[0]
        psi0 = gaussian_packet(x, -60.0, 8.0, 1.8)
        V = smoothed_barrier(x, 2.0, 1.0, fw * dx)
        nst = 24000                                    # T = 120
        psi, snap, diag = split_operator_evolve(
            psi0, x, V, dt=0.005, n_steps=nst, absorb_width=0,
            barrier_span=(-30.0, 30.0), sample_at=[nst])
        pl = diag["p_left"][-1]
        pr = diag["p_right"][-1]
        T = pr / (pl + pr)
        print(f"{fw:5.1f} {N:7} {dx:9.5f} {T:10.6f} {T - REF:+11.2e}")
    print()

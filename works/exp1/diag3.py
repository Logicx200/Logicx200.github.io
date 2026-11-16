"""定位 rk4_step 数值错误"""
import numpy as np
import physics
from physics import MU, J2, RE, KJ2

a, e, i, Om, w, M = 7200e3, 0.02, np.deg2rad(98.05), np.deg2rad(76.0), 0.5, 0.3
pos, vel = physics.coe2rv(*[np.atleast_1d(v) for v in (a, e, i, Om, w, M)])
x = np.concatenate([pos[0], vel[0]])
out = []

# 解析加速度
r = x[:3]
rn = np.linalg.norm(r)
acc_two = -MU / rn ** 3 * r
zz = 5.0 * r[2] ** 2 / rn ** 2
acc_j2 = KJ2 / rn ** 5 * np.array([(zz - 1) * r[0], (zz - 1) * r[1], (zz - 3) * r[2]])
out.append(f"|acc_two| = {np.linalg.norm(acc_two):.6e}  |acc_j2| = {np.linalg.norm(acc_j2):.6e}")
out.append(f"ratio j2/two = {np.linalg.norm(acc_j2)/np.linalg.norm(acc_two):.3e}")

# 手算内联的第一阶段
x1, y1, z1 = x[0], x[1], x[2]
r2 = x1 * x1 + y1 * y1 + z1 * z1
rr = np.sqrt(r2)
ir3 = 1.0 / (r2 * rr)
ir5 = ir3 / r2
f = KJ2 * ir5
out.append(f"r2={r2:.6e} ir3={ir3:.6e} ir5={ir5:.6e} f={f:.6e} KJ2={KJ2:.6e}")

H, h = 10.0, 2.5


def inline_deriv(x):
    x1, y1, z1 = x[..., 0], x[..., 1], x[..., 2]
    r2 = x1 * x1 + y1 * y1 + z1 * z1
    r = np.sqrt(r2)
    ir3 = 1.0 / (r2 * r)
    ir5 = ir3 / r2
    f = KJ2 * ir5
    zz = 5.0 * z1 * z1 / r2
    a = np.empty_like(x)
    a[..., 0] = -MU * x1 * ir3 + f * (zz - 1.0) * x1
    a[..., 1] = -MU * y1 * ir3 + f * (zz - 1.0) * y1
    a[..., 2] = -MU * z1 * ir3 + f * (zz - 3.0) * z1
    a[..., 3:] = x[..., 3:]
    return a


d_inline = inline_deriv(x)
out.append(f"inline deriv pos = {d_inline[:3]}")
out.append(f"numeric check    = {np.array([-MU*x[0]/rn**3+acc_j2[0], -MU*x[1]/rn**3+acc_j2[1], -MU*x[2]/rn**3+acc_j2[2]])}")
out.append(f"deriv vel part   = {d_inline[3:]}  vs actual v = {x[3:]}")

# 单步 rk4 展开
k1 = d_inline
u = x + (0.5 * h) * k1
k2 = inline_deriv(u)
u = x + (0.5 * h) * k2
k3 = inline_deriv(u)
u = x + h * k3
k4 = inline_deriv(u)
out.append(f"k1 = {k1}")
out.append(f"k2 = {k2}")
out.append(f"k3 = {k3}")
out.append(f"k4 = {k4}")
new = x + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
out.append(f"new state = {new}")

open("diag3.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))

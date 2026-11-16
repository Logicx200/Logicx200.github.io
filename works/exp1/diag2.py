"""隔离诊断 RK4 传播"""
import numpy as np
import physics, core

a, e, i, Om, w, M = 7200e3, 0.02, np.deg2rad(98.05), np.deg2rad(76.0), 0.5, 0.3
pos, vel = physics.coe2rv(*[np.atleast_1d(v) for v in (a, e, i, Om, w, M)])
x0 = np.concatenate([pos[0], vel[0]])
out = []
out.append(f"x0 = {x0}")

# RK4 单步
x = x0.copy()
for k in range(5):
    x = physics.rk4_step(x, 10.0)
out.append(f"after 5 steps of 10s: {x}")

# 长时积分: 逐步检查有限性
x = x0.copy()
bad = None
for k in range(720):
    x = physics.rk4_step(x, 10.0)
    if not np.isfinite(x).all():
        bad = k; break
    r = np.linalg.norm(x[:3])
    if k % 120 == 0:
        out.append(f"  step {k:4d}  r={r/1e3:10.3f} km  |v|={np.linalg.norm(x[3:])/1e3:.4f} km/s")
out.append(f"diverged at step {bad}")

# 与解析解对比 (2h)
from physics import MU
n = np.sqrt(MU / a ** 3)
pos_a, _ = physics.coe2rv(*[np.atleast_1d(v) for v in (a, e, i, Om, w, M + n * 7200.0)])
out.append(f"analytic end r = {np.linalg.norm(pos_a[0])/1e3:.3f} km")

# 与 propagate() 对比
tr = physics.propagate(x0, 7200.0, 10.0, 721)
out.append(f"propagate end r = {np.linalg.norm(tr[-1,:3])/1e3:.3f} km  finite={np.isfinite(tr).all()}")
out.append(f"propagate max|r| = {np.linalg.norm(tr[:,:3],axis=1).max()/1e3:.3f} km  min={np.linalg.norm(tr[:,:3],axis=1).min()/1e3:.3f} km")

# 计时: 单候选 vectorized
import time
oe = np.array([[a, e, i, Om, w, M]])
t0 = time.time()
for _ in range(20):
    core.sc_traj_batch(oe, 10.0, 7200.0)
out.append(f"sc_traj_batch 1 cand: {(time.time()-t0)/20*1e3:.2f} ms")
oe = np.repeat(oe, 200, 0)
t0 = time.time()
core.sc_traj_batch(oe, 10.0, 7200.0)
out.append(f"sc_traj_batch 200 cand: {(time.time()-t0)*1e3:.2f} ms -> {(time.time()-t0)/200*1e6:.0f} us/cand")

open("diag2.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))

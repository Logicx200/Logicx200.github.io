"""定位 E3 配对评估与 scan 不一致的问题"""
import os
import numpy as np
import core
from gate import make_cloud
from run_exp1 import make_tgrid, build_ephemeris, eval_pairs, scan

cloud = make_cloud(345, seed=7, rng_center=dict(a_sd=400e3, e_sd=0.06, i_sd=1.2, Om_sd=2.5))
tgrid10 = make_tgrid(dt=10.0)
eph10 = build_ephemeris(cloud, tgrid10)
tgrid30 = make_tgrid(dt=30.0)
eph30 = build_ephemeris(cloud, tgrid30)
shapes = np.load("sparse/e2_shapes.npy")
hits = np.load("sparse/e2_hits.npy")
nuniq = np.load("sparse/e2_nuniq.npy")
ph = core.phase_grid(12, 12)
good = np.flatnonzero(hits.any(axis=1))[:10]
out = [f"good = {good}", f"nuniq[good] max = {nuniq[good].max(1)}"]
seeds = shapes[good]
best = ph[[int(np.argmax(nuniq[s])) for s in good]]
out.append(f"best phase = {np.rad2deg(best)}")

# 1) scan 在 (seed, best_phase) 上是否命中
h1, _ = scan(seeds, best, cloud, tgrid10, eph10)
out.append(f"scan(seeds, best) diag = {np.diag(h1)}")

# 2) eval_pairs 同样输入
oe = np.concatenate([seeds, best], -1).astype(float)
h2 = eval_pairs(oe, cloud, tgrid10, eph10)
out.append(f"eval_pairs dt=10 = {h2.astype(int)}  (sum={h2.sum()})")
h3 = eval_pairs(oe, cloud, tgrid30, eph30)
out.append(f"eval_pairs dt=30 = {h3.astype(int)}  (sum={h3.sum()})")

# 3) 检查单点: 第 0 个
i = 0
oe1 = oe[i:i + 1]
out.append(f"single eval_pairs = {eval_pairs(oe1, cloud, tgrid30, eph30)}")
# 直接用 scan 同一配对 (S=1, P=1)
h4, n4 = scan(seeds[i:i + 1], best[i:i + 1], cloud, tgrid30, eph30)
out.append(f"scan single dt=30 = {h4[0,0]}, nuniq={n4[0,0]}")

open("diag_e3.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))

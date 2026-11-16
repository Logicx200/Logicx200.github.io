"""快速探测: scan 的速度与命中统计 (结果写入 probe.txt)"""
import numpy as np, time, sys
import core
from gate import make_cloud
from run_exp1 import scan, make_tgrid, build_ephemeris

cloud = make_cloud(345, seed=7)
tgrid = make_tgrid(dt=10.0)
t0 = time.time(); eph = build_ephemeris(cloud, tgrid); t_eph = time.time() - t0
rng = np.random.default_rng(11)
shapes = core.sample_shapes(300, rng)
ph = core.phase_grid(12, 12)
t0 = time.time(); hits, nu = scan(shapes, ph, cloud, tgrid, eph); el = time.time() - t0
lines = [
    f"ephemeris {eph[0].shape} built in {t_eph:.1f}s",
    f"scan: shapes={len(shapes)} phases={len(ph)} cand={hits.size} elapsed={el:.1f}s",
    f"hit fraction = {hits.mean()*100:.4f}%  ({int(hits.sum())} events)",
    f"shapes with any feasible phase = {int(hits.any(1).sum())}/{len(shapes)}",
    f"max uniq per candidate = {int(nu.max())}   mean uniq = {nu.mean():.4f}",
    f"uniq on feasible = {nu[hits].mean() if hits.any() else 0:.2f}",
]
open("probe.txt", "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))

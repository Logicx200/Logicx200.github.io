"""性能与数值诊断 (结果写入 diag.txt)"""
import numpy as np, time
import core, physics
from gate import make_cloud
from run_exp1 import make_tgrid, build_ephemeris

out = []
cloud = make_cloud(345, seed=7)
rng = np.random.default_rng(11)
sh = core.sample_shapes(3000, rng)
rp = sh[:, 0] * (1 - sh[:, 1]) - physics.RE
ra = sh[:, 0] * (1 + sh[:, 1]) - physics.RE
out.append(f"a range  : {sh[:,0].min()/1e3:.1f} .. {sh[:,0].max()/1e3:.1f} km")
out.append(f"e range  : {sh[:,1].min():.5f} .. {sh[:,1].max():.5f}")
out.append(f"perigee alt range: {rp.min()/1e3:.1f} .. {rp.max()/1e3:.1f} km")
out.append(f"apo alt range    : {ra.min()/1e3:.1f} .. {ra.max()/1e3:.1f} km")
out.append(f"shapes with perigee < 200 km: {(rp < 200e3).sum()} / {len(sh)}")
out.append(f"shapes with perigee < 0    : {(rp < 0).sum()}")

tgrid = make_tgrid(dt=10.0)
t0 = time.time(); eph = build_ephemeris(cloud, tgrid); out.append(f"ephemeris {eph[0].shape} in {time.time()-t0:.2f}s")

# 单个候选的传播耗时
oe = np.stack([sh[:20, 0], sh[:20, 1], sh[:20, 2], sh[:20, 3],
               np.zeros(20), np.zeros(20)], -1)
t0 = time.time(); tr = core.sc_traj_batch(oe, 10.0, 7200.0); dt1 = time.time() - t0
out.append(f"sc_traj_batch 20 cand: {dt1*1000:.1f} ms  -> {dt1/20*1e6:.0f} us/cand")
out.append(f"finite? {np.isfinite(tr).all()}   r_end={np.linalg.norm(tr[:,-1,:3],axis=1)[:5]}")

# 每候选的窄相位+判定耗时
deb_pos, deb_vel = eph
deb_box = np.stack([deb_pos.min(1), deb_pos.max(1)], 1)
pos = tr[:, :, :3]
lo = pos.min(1) - 200e3; hi = pos.max(1) + 200e3
keep = (deb_box[None, :, 1, :] >= lo[:, None, :]).all(-1) & (deb_box[None, :, 0, :] <= hi[:, None, :]).all(-1)
out.append(f"bbox filter keeps (mean per cand): {keep.sum(1).mean():.1f} / 345")
t0 = time.time()
cnt = 0
for i in range(20):
    di = np.flatnonzero(keep[i])
    p = pos[i]; v = tr[i, :, 3:]
    for k in range(0, len(tgrid)):
        d = deb_pos[di, k, :] - p[k]
        dist2 = np.einsum('nd,nd->n', d, d)
        mm = np.flatnonzero(dist2 < 900e6)
        if mm.size:
            vv = deb_vel[di[mm], k, :] - v[k]
            rv2 = np.einsum('nd,nd->n', vv, vv)
            ok = mm[rv2 < 22500.0]
            cnt += ok.size
out.append(f"detail loop per cand: {(time.time()-t0)/20*1e3:.2f} ms  (hits={cnt})")
open("diag.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))

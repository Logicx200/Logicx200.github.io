"""补算 E3/E4 并合并进 results.json (E1/E2 复用已存盘数据, 不重跑扫描)

用法: python run_e34_only.py dense|sparse
"""
import json
import os
import sys
import numpy as np

from gate import make_cloud
from run_exp1 import make_tgrid, build_ephemeris, exp3_correlation, exp4_predictability
import core

tag = sys.argv[1] if len(sys.argv) > 1 else 'dense'
CFG = {
    'dense': dict(a_sd=40e3, e_sd=0.006, i_sd=0.12, Om_sd=0.25),
    'sparse': dict(a_sd=400e3, e_sd=0.06, i_sd=1.2, Om_sd=2.5),
}[tag]

cloud = make_cloud(345, seed=7, rng_center=CFG)
tgrid = make_tgrid(dt=10.0)
eph = build_ephemeris(cloud, tgrid)
hits = np.load(os.path.join(tag, 'e2_hits.npy'))
nuniq = np.load(os.path.join(tag, 'e2_nuniq.npy'))
shapes = np.load(os.path.join(tag, 'e2_shapes.npy'))
ref = (cloud[:, 0].mean(), cloud[:, 1].mean(), cloud[:, 2].mean(), cloud[:, 3].mean())

e3 = exp3_correlation(cloud, shapes, hits, eph, tag=tag)
e4 = exp4_predictability(cloud, shapes, core.phase_grid(12, 12), hits, nuniq, ref)

p = os.path.join(tag, 'results.json')
res = json.load(open(p, encoding='utf-8'))
res['E3'] = e3
res['E4'] = e4
json.dump(res, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2, default=float)
print("merged E3/E4 into", p)

"""仅补跑 E5 (稠密情形 E5 超时), 并把结果合并进 results.json"""
import json
import os
import sys
import numpy as np

import core
from gate import make_cloud
from run_exp1 import make_tgrid, build_ephemeris, exp5_budget

tag = sys.argv[1] if len(sys.argv) > 1 else 'dense'
cloud = make_cloud(345, seed=7, rng_center=dict(a_sd=40e3, e_sd=0.006, i_sd=0.12, Om_sd=0.25))
tgrid = make_tgrid(dt=10.0)
eph = build_ephemeris(cloud, tgrid)
e5 = exp5_budget(cloud, eph, n_pool=4000, budget=40, nw=8, nM=8)
p = os.path.join(tag, 'results.json')
with open(p, encoding='utf-8') as f:
    res = json.load(f)
res['E5'] = e5
res['meta'] = dict(res.get('meta', {}), e5_budget=40, e5_grid='8x8')
with open(p, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2, default=float)
print("E5 merged into", p)

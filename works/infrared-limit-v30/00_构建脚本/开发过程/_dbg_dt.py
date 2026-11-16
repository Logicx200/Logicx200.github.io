# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "04_模型代码"))
import numpy as np
from irrecog import chain, critical

base = chain.baseline_scenario()
r_ref = 16.216
bs = critical.BandState(base, r_ref)
print("lam_eff", bs.lam_eff, "r_slant", bs.r_slant_km, "tau", bs.tau_band,
      "t_app_b", bs.t_app_b, "dT_app(20)=", bs.dT_app())
dts = np.array([-8., -4., -1., 0., 1., 4., 8., 20.])
d_many = bs.dT_app_many(base.bg_temp_c + dts)
print("dT_app_many=", d_many)
pv = critical.probabilities(d_many, base.sensor, bs.lam_eff, bs.r_slant_km,
                            base.target.d_eff_m, base.cn2, base.n50_set)
print("P_many=", pv["recognize"])
for dT in (-8., -4., -1., 0., 1., 4., 8., 20.):
    row = chain.evaluate(base.with_(target_temp_c=base.bg_temp_c + dT), r_ref)
    print(f"dT={dT:5.1f} chain dT_app={row['dT_app_K']:7.3f} P={row['P_rec']:.4f}")
print()
print("delta_t_for_p:", critical.delta_t_for_p(base, r_ref))
print("delta_t_for_p@10:", critical.delta_t_for_p(base, 10.0))

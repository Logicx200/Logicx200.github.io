# -*- coding: utf-8 -*-
import sys, os
import numpy as np
p = r"F:\DeepSeek工作区\红外识别极限重构_V3.0\07_光谱数据\xsect_mwir.npz"
if os.path.exists(p):
    d = np.load(p, allow_pickle=False)
    print("keys:", d.files)
    print("nu:", d["nu"][0], d["nu"][-1], len(d["nu"]))
    for k in d.files:
        if k != "nu":
            a = d[k]
            print(f"  {k}: shape={a.shape} min={np.nanmin(a):.3e} max={np.nanmax(a):.3e}")
else:
    print("missing")

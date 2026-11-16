# -*- coding: utf-8 -*-
import csv
import os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
d = np.load(os.path.join(HERE, "_dtapp_grid.npz"))
s = d["sigma"]; p = d["pwv"]; dt = d["dt"]; tb = d["tau_band"]
out = os.path.join(HERE, "视在温差网格_3-5um_夜间.csv")
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["sigma_a550_km-1", "PWV_cm", "dT_app_K", "tau_band"])
    for j in range(len(p)):
        for i in range(len(s)):
            w.writerow([round(float(s[i]), 5), round(float(p[j]), 3),
                        round(float(dt[j, i]), 4), round(float(tb[j, i]), 4)])
print("saved", out)

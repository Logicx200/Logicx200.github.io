# -*- coding: utf-8 -*-
"""实验矩阵冒烟测试：全部扫描各跑一次，检查无异常并计时。"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))

import numpy as np
from irrecog import experiments as E

if __name__ == "__main__":
    grid = np.geomspace(0.5, 320.0, 14)
    t0 = time.time()
    res = E.run_all(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "03_数据", "_smoke"),
                    r_grid=grid, verbose=True)
    print("\n长表", res["long"].shape, "汇总", res["summary"].shape)
    print("列数", len(res["summary"].columns))
    print("耗时 %.1f s" % (time.time() - t0))
    cols = ["sweep_id", "sweep_value", "target", "R50_ground_km", "R_res_analytic_km", "eta"]
    print(res["summary"][cols].head(12).to_string())
    print("\nR50 缺失行数:", res["summary"]["R50_ground_km"].isna().sum(), "/", len(res["summary"]))

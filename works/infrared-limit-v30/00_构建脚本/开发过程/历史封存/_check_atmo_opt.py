# -*- coding: utf-8 -*-
"""优化后 atmosphere 的等价性与性能校验。"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))
import numpy as np
import irrecog.atmosphere as A


def main():
    a = A.Atmo()
    for band in ("MWIR", "LWIR"):
        ts, lp = [], []
        for r in (1.0, 10.0, 20.0):
            st = A.spectral_state(a, band, r, 0.0, 8000.0)
            ts.append(st["tau_band"]); lp.append(st["l_path"])
        print(f"{band}: tau 1/10/20 km = " + " / ".join(f"{x:.4f}" for x in ts)
              + "  | Lp = " + " / ".join(f"{x:.3f}" for x in lp)
              + f"  Npts={len(A.band_grid(band))}")
    for band in ("MWIR", "LWIR"):
        t0 = time.time()
        n = 40
        for i in range(n):
            A.spectral_state(a, band, 1.0 + i * 0.4, 0.0, 8000.0)
        print(f"{band} 耗时 {(time.time()-t0)/n*1000:.2f} ms/call")
    # 物种清单
    for band in ("MWIR", "LWIR"):
        lam, species, temps, src = A._xsect_band_grid(band)
        print(f"{band} species={list(species)} temps={temps} file={os.path.basename(src)}")

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""设计探针：不同平台高度/大气条件下，识别极限由分辨率还是大气支配。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_模型代码"))

import numpy as np
from irrecog import chain, critical, sensor as S, target as T
from irrecog.params import TARGETS


def probe():
    print("=== 平台高度 × 大气：F16 / 尼米兹 的 tau 与 N ===")
    for alt in (100.0, 500.0, 2000.0, 8000.0):
        sen = S.make_sensor("MWIR", platform_h_m=alt)
        for aod in (0.1, 0.587, 2.0):
            scn = chain.baseline_scenario().with_sensor(platform_h_m=alt).with_(aod550=aod)
            line = []
            for r in (5.0, 20.0, 60.0):
                ev = chain.evaluate(scn, r)
                line.append(f"R{r:>4.0f}:tau={ev['tau_band']:.2f},dT={ev['dT_app_K']:.2f},"
                            f"N={ev['n_cycles']:.0f},P={ev['P_rec']:.2f}")
            print(f"  h={alt:6.0f} m AOD={aod:5.2f}  " + " | ".join(line))
        print()


def probe_r50():
    print("=== R50（地面 km）随平台高度变化 ===")
    targets = ["HM", "F16", "AGZFSC", "ALBK"]
    print(f"{'alt':>8} " + "".join(f"{t:>12}" for t in targets))
    for alt in (100.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0, 12000.0):
        row = []
        for tk in targets:
            scn = chain.baseline_scenario(target_key=tk).with_sensor(platform_h_m=alt)
            res = critical.range_for_p(scn, "recognize", 0.5)
            row.append(f"{res['r_km']:12.2f}")
            row[-1] = row[-1] + ("" if not res["censored"] else "*")
        print(f"{alt:8.0f} " + "".join(row))


def probe_sweeps():
    print("\n=== 单变量敏感度（h=8000m, F16 / 尼米兹）===")
    for tk in ("F16", "NIMITZ"):
        base = chain.baseline_scenario(target_key=tk)
        r50_base = critical.r50(base)
        print(f"  {tk}: 基准 R50={r50_base:.2f} km")
        for name, vals, mk in [
            ("AOD", (0.05, 0.3, 0.6, 1.5, 3.0), lambda v: dict(aod550=v)),
            ("PWV", (0.3, 1.3, 3.0, 6.0), lambda v: dict(pwv_cm=v)),
            ("Cn2", (1e-16, 1e-15, 1e-14, 1e-13), lambda v: dict(cn2=v)),
            ("alpha", (0.3, 0.8, 1.3, 1.8), lambda v: dict(alpha=v)),
        ]:
            out = []
            for v in vals:
                scn = base.with_(**mk(v))
                out.append(f"{v:g}:{critical.r50(scn):.1f}")
            print(f"    {name:<6} " + "  ".join(out))


if __name__ == "__main__":
    probe()
    probe_r50()
    probe_sweeps()

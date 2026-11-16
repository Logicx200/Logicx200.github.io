# -*- coding: utf-8 -*-
"""Build cross-section npz with H2O (full) and CO2 (4.3 um band) only."""
import os
import time

import numpy as np
import hapi

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "_hapi_db")
hapi.db_begin(DB)

T, P = 283.15, 1.01325
WN_MIN, WN_MAX, STEP = 2000.0, 3400.0, 0.05
GRID = np.arange(WN_MIN, WN_MAX + STEP / 2, STEP)

out = {}

for name, M, I, table, wmin, wmax in [
    ("H2O", 1, 1, "H2O_2000_3400", 2000, 3400),
    ("CO2", 2, 1, "CO2_2280_2400", 2280, 2400),
    ("CH4", 6, 1, "CH4_2950_3150", 2950, 3150),
]:
    t0 = time.time()
    nu, xs = hapi.absorptionCoefficient_Voigt(
        Components=[(M, I)],
        SourceTables=[table],
        Environment={"p": P, "T": T},
        WavenumberRange=[wmin, wmax],
        WavenumberStep=STEP,
        HITRAN_units=True,
        Diluent={"air": 1},
    )
    nu = np.asarray(nu, float)
    xs = np.asarray(xs, float)
    if nu[0] > nu[-1]:
        nu, xs = nu[::-1], xs[::-1]
    start = int(round((wmin - WN_MIN) / STEP))
    npts = int(round((wmax - wmin) / STEP)) + 1
    full = np.zeros_like(GRID)
    full[start:start + npts] = xs
    out[name] = full
    print(name, "max", float(np.nanmax(xs)), round(time.time() - t0, 1), "s", flush=True)

np.savez_compressed(os.path.join(HERE, "_xsect_3_5um.npz"), nu=GRID, **out)
print("saved", flush=True)

# -*- coding: utf-8 -*-
"""Fetch remaining HITRAN gases (3-5 um) and compute cross-sections on a common grid."""
import os
import time

import numpy as np
import hapi

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "_hapi_db")
os.makedirs(DB, exist_ok=True)
hapi.db_begin(DB)

T, P = 283.15, 1.01325
WN_MIN, WN_MAX, WN_STEP = 2000.0, 3400.0, 0.05
GRID = np.arange(WN_MIN, WN_MAX + WN_STEP / 2, WN_STEP)

# 全谱段直接算；窄谱段先取线再算
SPECIES = [
    # name, M, I, table, wmin, wmax
    ("H2O", 1, 1, "H2O_2000_3400", 2000, 3400),
    ("CO2", 2, 1, "CO2_2280_2400", 2280, 2400),
    ("O3", 3, 1, "O3_2000_2250", 2000, 2250),
    ("N2O", 4, 1, "N2O_2050_2350", 2050, 2350),
    ("CO", 5, 1, "CO_2000_2300", 2000, 2300),
    ("CH4", 6, 1, "CH4_2800_3200", 2800, 3200),
]

xs_full = {}
for name, M, I, table, wmin, wmax in SPECIES:
    t0 = time.time()
    datafile = os.path.join(DB, table + ".data")
    if not (os.path.exists(datafile) and os.path.getsize(datafile) > 1000):
        print("fetch", name, wmin, wmax, flush=True)
        hapi.fetch(table, M, I, wmin, wmax)
    print("calc xsect", name, flush=True)
    nu, xs = hapi.absorptionCoefficient_Voigt(
        Components=[(M, I)],
        SourceTables=[table],
        Environment={"p": P, "T": T},
        WavenumberRange=[wmin, wmax],
        WavenumberStep=WN_STEP,
        HITRAN_units=True,
        Diluent={"air": 1},
    )
    nu = np.asarray(nu, dtype=float)
    xs = np.asarray(xs, dtype=float)
    if nu[0] > nu[-1]:
        nu, xs = nu[::-1], xs[::-1]
    start = int(round((wmin - WN_MIN) / WN_STEP))
    npts = int(round((wmax - wmin) / WN_STEP)) + 1
    assert start >= 0 and start + npts <= len(GRID), (name, start, npts, len(GRID))
    assert len(xs) == npts, (name, len(xs), npts)
    full = np.zeros_like(GRID)
    full[start:start + npts] = xs
    xs_full[name] = full
    print("  done", name, "nlines", len(xs), round(time.time() - t0, 1), "s",
          "max", float(np.nanmax(xs)), flush=True)

np.savez_compressed(os.path.join(HERE, "_xsect_3_5um.npz"), nu=GRID, **xs_full)
print("saved _xsect_3_5um.npz", flush=True)

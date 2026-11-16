# -*- coding: utf-8 -*-
"""Slow HITRAN fetch for minor 3-5 um gases, then append to cross-section npz."""
import os
import time

import numpy as np
import hapi

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "_hapi_db")
hapi.db_begin(DB)

T, P, STEP, WN0 = 283.15, 1.01325, 0.05, 2000.0

SPECIES = [
    ("N2O", 4, 1, "N2O_2050_2350", 2050, 2350),
    ("CO", 5, 1, "CO_2000_2300", 2000, 2300),
    ("O3", 3, 1, "O3_2000_2250", 2000, 2250),
]

existing = np.load(os.path.join(HERE, "_xsect_3_5um.npz"))
GRID = existing["nu"]
out = {k: existing[k] for k in existing.files if k != "nu"}

for name, M, I, table, wmin, wmax in SPECIES:
    if name in out:
        print("have", name, flush=True)
        continue
    data = os.path.join(DB, table + ".data")
    header = os.path.join(DB, table + ".header")
    ok = os.path.exists(data) and os.path.exists(header) and os.path.getsize(data) > 1000
    if not ok:
        print("fetch", name, flush=True)
        try:
            hapi.fetch(table, M, I, wmin, wmax)
        except Exception as e:
            print("ERR fetch", name, e, flush=True)
            continue
    print("xsect", name, flush=True)
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
    start = int(round((wmin - WN0) / STEP))
    npts = int(round((wmax - wmin) / STEP)) + 1
    if len(xs) != npts:
        print("length mismatch", name, len(xs), npts, flush=True)
        continue
    full = np.zeros_like(GRID)
    full[start:start + npts] = xs
    out[name] = full
    print("done", name, float(np.nanmax(xs)), flush=True)
    np.savez_compressed(os.path.join(HERE, "_xsect_3_5um.npz"), nu=GRID, **out)

print("all done", list(out), flush=True)

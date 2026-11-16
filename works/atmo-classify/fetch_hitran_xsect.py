# -*- coding: utf-8 -*-
"""Fetch HITRAN lines and compute absorption cross-sections for 3-5 um gases."""
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "_hapi_db")
os.makedirs(DB, exist_ok=True)

import hapi

hapi.db_begin(DB)

SPECIES = [
    ("H2O", 1, 1, "H2O_2000_3400"),
    ("CO2", 2, 1, "CO2_2000_3400"),
    ("O3", 3, 1, "O3_2000_3400"),
    ("N2O", 4, 1, "N2O_2000_3400"),
    ("CO", 5, 1, "CO_2000_3400"),
    ("CH4", 6, 1, "CH4_2000_3400"),
]

WN_MIN, WN_MAX = 2000.0, 3400.0
WN_STEP = 0.05
T, P = 283.15, 1.01325  # K, atm

out = {}
for name, M, I, table in SPECIES:
    t0 = time.time()
    datafile = os.path.join(DB, table + ".data")
    if not os.path.exists(datafile) or os.path.getsize(datafile) < 1000:
        print("fetch", name, flush=True)
        hapi.fetch(table, M, I, WN_MIN, WN_MAX)
    else:
        print("cached", name, flush=True)
    print("  computing xsect", name, flush=True)
    nu, xs = hapi.absorptionCoefficient_Voigt(
        Components=[(M, I)],
        SourceTables=[table],
        Environment={"p": P, "T": T},
        WavenumberRange=[WN_MIN, WN_MAX],
        WavenumberStep=WN_STEP,
        HITRAN_units=True,
        Diluent={"air": 1},
    )
    out[name] = np.asarray(xs, dtype=np.float64)
    print("  done", name, len(nu), "pts", round(time.time() - t0, 1), "s",
          "max xs", float(np.nanmax(xs)), flush=True)

np.savez_compressed(
    os.path.join(HERE, "_xsect_3_5um.npz"),
    nu=np.asarray(nu),
    **{k: v for k, v in out.items()},
)
print("saved _xsect_3_5um.npz", flush=True)

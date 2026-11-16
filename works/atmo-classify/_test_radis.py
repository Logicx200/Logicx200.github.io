# -*- coding: utf-8 -*-
import time
import numpy as np

t0 = time.time()
import radis
print("radis", radis.__version__, "import", round(time.time() - t0, 2), "s")

from radis import calc_spectrum

t0 = time.time()
s = calc_spectrum(
    2100, 2300,          # cm-1 range (4.35-4.76 um) test only
    molecule="H2O",
    isotope="1",
    pressure=1.01325,
    Tgas=283.15,
    mole_fraction=0.01,
    path_length=2e5,     # cm (2 km)
    databank="hitran",
    verbose=False,
)
print("calc", round(time.time() - t0, 1), "s")
print(s)
print("waves", s.get_wavenumber().min(), s.get_wavenumber().max(), len(s.get_wavenumber()))
print("trans", np.nanmin(s.get("transmittance_noslit")), np.nanmean(s.get("transmittance_noslit")))
print("keys", list(s.get_vars()))

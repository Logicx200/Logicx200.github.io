# -*- coding: utf-8 -*-
import numpy as np
import lowtran

# 水平路径，地面，用户大气：p=1013.25 hPa, T=283.15 K, RH 可调
def run(rh, rng_km=2.0, temp=283.15):
    c1 = {
        "model": 0,      # user atmosphere
        "itype": 1,      # horizontal path
        "iemsct": 1,     # thermal radiance
        "im": 1,
        "ird1": 1,
        "h1": 0.0,
        "h2": 0.0,
        "zmdl": [0.0],
        "angle": 0.0,
        "range_km": rng_km,
        "p": [1013.25],
        "t": [temp],
        "wmol": [rh, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "wlshort": 3000.0,
        "wllong": 5000.0,
        "wlstep": 20.0,
        "time": [None],
    }
    return lowtran.golowtran(c1)

TR = run(60.0)
wl = TR.wavelength_nm.values
tr = TR.transmission.values[0, :, 0]
rad = TR.radiance.values[0, :, 0]
print("wl shape", wl.shape, "range", wl.min(), wl.max())
print("trans samples", [(round(float(wl[i]),1), round(float(tr[i]),4), round(float(rad[i]),6)) for i in range(0, len(wl), 10)])
print("rad min/max", float(np.nanmin(rad)), float(np.nanmax(rad)))

# Planck at 283.15K, W/cm^2/sr/um
def planck_lam(lam_um, T):
    h = 6.626e-34; c = 3e8; k = 1.381e-23
    lam = lam_um * 1e-6
    B = 2*h*c**2/lam**5 / (np.exp(h*c/(lam*k*T))-1)  # W/m^2/sr/m
    return B * 1e-4 * 1e-6  # W/m^2/sr/m -> W/cm^2/sr/um

for i in range(0, len(wl), 10):
    lam_um = wl[i]/1000.0
    print(round(float(wl[i]),1), "T", round(float(tr[i]),4), "rad", round(float(rad[i]),6),
          "planck", round(float(planck_lam(lam_um, 283.15)),6))

print("RH effect:")
for rh in [20, 50, 90]:
    T = run(rh)
    wl2 = T.wavelength_nm.values
    tr2 = T.transmission.values[0,:,0]
    mask = (wl2>3500)&(wl2<4000)
    print("RH", rh, "mean tau 3.5-4.0um", float(np.nanmean(tr2[mask])))

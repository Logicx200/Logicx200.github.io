# -*- coding: utf-8 -*-
"""Export the computed spectrum to CSV plus a band-summary table."""
import os, json
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'output')
os.makedirs(OUT, exist_ok=True)

d = np.load(os.path.join(BASE, 'slant_spectrum.npz'))
nu = d['grid']
tau_tot = d['tau_total']

# ---- decimate to 0.05 cm^-1 for the CSV ----
step_out = 0.05
idx = np.searchsorted(nu, np.arange(nu[0], nu[-1], step_out))
idx = np.clip(idx, 0, len(nu) - 1)
df = pd.DataFrame({
    'wavenumber_cm-1': nu[idx].round(4),
    'wavelength_um': (1e4 / nu[idx]).round(4),
    'T_H2O': d['tr_H2O'][idx].round(6),
    'T_CO2': d['tr_CO2'][idx].round(6),
    'T_CH4': d['tr_CH4'][idx].round(6),
    'T_total': d['tr_total'][idx].round(6),
    'tau_total': tau_tot[idx].round(6),
})
csv_main = os.path.join(OUT, 'slant_transmittance_500-5000cm-1.csv')
df.to_csv(csv_main, index=False, encoding='utf-8-sig')
print('wrote', csv_main, len(df), 'rows')

# ---- band summary (mean transmittance over windows) ----
windows = [(2.0, 2.5), (2.5, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0),
           (6.0, 8.0), (8.0, 10.0), (10.0, 12.0), (12.0, 14.0), (14.0, 16.0),
           (16.0, 20.0)]
rows = []
for a, b in windows:
    wl = 1e4 / nu
    sel = (wl >= a) & (wl < b)
    rows.append(dict(
        band_um='%.1f-%.1f' % (a, b),
        wavenumber_cm1='%.0f-%.0f' % (1e4 / b, 1e4 / a),
        T_total_mean=round(float(d['tr_total'][sel].mean()), 4),
        T_H2O_mean=round(float(d['tr_H2O'][sel].mean()), 4),
        T_CO2_mean=round(float(d['tr_CO2'][sel].mean()), 4),
        T_CH4_mean=round(float(d['tr_CH4'][sel].mean()), 4),
        tau_total_mean=round(float(tau_tot[sel].mean()), 3),
    ))
sumdf = pd.DataFrame(rows)
csv_sum = os.path.join(OUT, 'band_mean_transmittance.csv')
sumdf.to_csv(csv_sum, index=False, encoding='utf-8-sig')
print(sumdf.to_string(index=False))
print('wrote', csv_sum)

# ---- layer table ----
import atmo
L = atmo.build_layers(24)
lay = pd.DataFrame({
    'layer': np.arange(1, 25),
    'z_mid_km': np.round(L['z'], 3),
    'T_K': np.round(L['T'], 2),
    'p_hPa': np.round(L['p_hpa'], 2),
    'slant_len_km': np.round(L['ds_cm'] / 1e5, 3),
    'n_H2O_cm-3': L['n_h2o'].astype(float),
    'n_CO2_cm-3': L['n_co2'].astype(float),
    'n_CH4_cm-3': L['n_ch4'].astype(float),
})
lay.to_csv(os.path.join(OUT, 'path_layers.csv'), index=False, encoding='utf-8-sig')
print('wrote layer table')

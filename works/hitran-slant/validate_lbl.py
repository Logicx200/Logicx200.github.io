# -*- coding: utf-8 -*-
"""Validation of the in-house LBL against HAPI's absorptionCoefficient_Voigt.

Method: fetch a small H2O window (1580-1620 cm-1) for all isotopologues with
HAPI, build the same compact table our code uses, then compare the cross
section (per molecule, natural abundance applied) from both codes.
"""
import os, sys
import numpy as np

BASE = r'F:\DeepSeek工作区\hitran_slant'
sys.path.insert(0, BASE)
import hapi
import lbl

hapi.db_begin(os.path.join(BASE, 'db'))

NU0, NU1, STEP = 1580.0, 1620.0, 0.002
T, P, X = 296.0, 1.0, 0.01

tables = []
for iso in (1, 2, 3, 4):
    name = 'H2O_iso%d' % iso
    try:
        hapi.fetch(name, 1, iso, NU0 - 25, NU1 + 25)
        tables.append(name)
    except Exception as e:
        print('fetch failed', iso, e)

env = {'T': T, 'p': P, 'mole_fraction': X}
res = hapi.absorptionCoefficient_Voigt(SourceTables=tables, Environment=env,
                                       WavenumberRange=[NU0, NU1],
                                       WavenumberStep=STEP,
                                       WavenumberWingHW=25.0)
nu_h = np.asarray(res['wavenumber'])
alpha_h = np.asarray(res['absorption_coefficient'])   # cm^-1
n_air = P * 101325.0 / (1.380649e-23 * T) / 1e6
n_h2o = X * n_air
sigma_hapi = alpha_h / n_h2o

# our implementation on the same line set
rows = []
for name in tables:
    iso = int(name[-1])
    with open(os.path.join(BASE, 'db', name + '.data'), encoding='utf-8') as f:
        for line in f:
            if len(line) < 67:
                continue
            rows.append([iso, float(line[3:15]), float(line[15:25]),
                         float(line[35:40]), float(line[40:45]),
                         float(line[45:55]), float(line[55:59]), float(line[59:67])])
arr = np.array(rows)
np.savez_compressed(os.path.join(BASE, 'lines', '_val_H2O.npz'),
                    iso=arr[:, 0].astype(np.int16), nu=arr[:, 1], sw=arr[:, 2],
                    gair=arr[:, 3], gself=arr[:, 4], elower=arr[:, 5],
                    nair=arr[:, 6], delta=arr[:, 7])
mol = lbl.MolLines(os.path.join(BASE, 'lines', '_val_H2O.npz'), 1, hapi.ISO,
                   hapi.partitionSum)
grid = np.arange(NU0, NU1 + STEP / 2, STEP)
qT = np.array([hapi.partitionSum(1, i, T) for i in mol.iso_uniq])
sigma_ours = mol.sigma(T, P, X, grid, STEP, qT)

sig_h = np.interp(grid, nu_h, sigma_hapi)
rel = (sigma_ours - sig_h) / np.maximum(sig_h, 1e-30)
print('grid', grid.size, 'max sigma ours %.4g hapi %.4g' % (sigma_ours.max(), sig_h.max()))
print('median rel diff %.2e   max |rel| %.2e' % (np.median(np.abs(rel)), np.abs(rel).max()))
print('mean rel diff %.2e' % rel.mean())

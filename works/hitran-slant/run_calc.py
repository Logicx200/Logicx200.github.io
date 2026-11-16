# -*- coding: utf-8 -*-
"""Compute slant-path optical depth and transmittance (HITRAN2020 LBL).

Usage examples
--------------
python run_calc.py --gmin 500 --gmax 5000 --step 0.01 --out slant_spectrum
python run_calc.py --gmin 714 --gmax 1250 --step 0.002 --out slant_8_14um
"""
import os, sys, time, json, argparse
import numpy as np
import multiprocessing as mp

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import hapi
import atmo
import lbl

DB = os.path.join(BASE, 'db')
LINES = os.path.join(BASE, 'lines')
OUT = os.path.join(BASE, 'results')
os.makedirs(OUT, exist_ok=True)

MOLS = {'H2O': 1, 'CO2': 2, 'CH4': 6}
XKEY = {'H2O': 'x_h2o', 'CO2': 'x_co2', 'CH4': 'x_ch4'}
NKEY = {'H2O': 'n_h2o', 'CO2': 'n_co2', 'CH4': 'n_ch4'}

_G = {}


def init_worker(nlayers, gmin, gmax, step):
    hapi.db_begin(DB)
    _G['lines'] = {m: lbl.MolLines(os.path.join(LINES, m + '.npz'), M,
                                   hapi.ISO, hapi.partitionSum)
                   for m, M in MOLS.items()}
    _G['layers'] = atmo.build_layers(nlayers)
    _G['grid'] = np.arange(gmin, gmax + step / 2, step)
    _G['step'] = step


def work(task):
    mol, i = task
    L = _G['layers']
    grid = _G['grid']
    molL = _G['lines'][mol]
    qT = np.array([hapi.partitionSum(molL.M, iso, L['T'][i])
                   for iso in molL.iso_uniq])
    sig = molL.sigma(L['T'][i], L['p_atm'][i], L[XKEY[mol]][i],
                     grid, _G['step'], qT)
    tau = sig * L[NKEY[mol]][i] * L['ds_cm'][i]
    return mol, i, tau.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--layers', type=int, default=24)
    ap.add_argument('--procs', type=int, default=16)
    ap.add_argument('--gmin', type=float, default=500.0)
    ap.add_argument('--gmax', type=float, default=5000.0)
    ap.add_argument('--step', type=float, default=0.01)
    ap.add_argument('--out', default='slant_spectrum')
    args = ap.parse_args()

    n = args.layers
    grid = np.arange(args.gmin, args.gmax + args.step / 2, args.step)
    tasks = [(m, i) for m in MOLS for i in range(n)]
    t0 = time.time()
    done = 0
    acc = {m: np.zeros(grid.size) for m in MOLS}
    with mp.Pool(args.procs, initializer=init_worker,
                 initargs=(n, args.gmin, args.gmax, args.step)) as pool:
        for mol, i, tau in pool.imap_unordered(work, tasks):
            acc[mol] += tau
            done += 1
            if done % 6 == 0 or done == len(tasks):
                print('[progress %d/%d] %s layer %02d  max tau=%.3g  (%.0fs)'
                      % (done, len(tasks), mol, i, tau.max(), time.time() - t0),
                      flush=True)

    tau = acc
    tau_tot = tau['H2O'] + tau['CO2'] + tau['CH4']
    tr = {m: np.exp(-tau[m]) for m in MOLS}
    tr_tot = np.exp(-tau_tot)

    np.savez_compressed(os.path.join(BASE, args.out + '.npz'),
                        grid=grid,
                        tau_H2O=tau['H2O'], tau_CO2=tau['CO2'],
                        tau_CH4=tau['CH4'], tau_total=tau_tot,
                        tr_H2O=tr['H2O'], tr_CO2=tr['CO2'],
                        tr_CH4=tr['CH4'], tr_total=tr_tot)
    meta = dict(step=args.step, grid_min=args.gmin, grid_max=args.gmax,
                nlayers=n,
                geometry='platform 8 km, ground range 20 km, slant 21.541 km',
                atmosphere='USSA76 T/p; H2O 7.5 g/m3 exp(-z/2km); CO2 415 ppm; CH4 1.9 ppm')
    with open(os.path.join(BASE, args.out + '.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print('TOTAL %.0fs  -> %s.npz' % (time.time() - t0, args.out), flush=True)


if __name__ == '__main__':
    main()

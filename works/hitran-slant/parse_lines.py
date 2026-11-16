# -*- coding: utf-8 -*-
"""Parse raw HITRAN .par chunks into compact per-molecule npz arrays."""
import os, sys, glob
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import hapi

hapi.db_begin(os.path.join(BASE, 'db'))
RAW = os.path.join(BASE, 'db_raw')
OUT = os.path.join(BASE, 'lines')
os.makedirs(OUT, exist_ok=True)
MOLS = {'H2O': 1, 'CO2': 2, 'CH4': 6}

COLS = dict(nu=(3, 15), sw=(15, 25), gair=(35, 40), gself=(40, 45),
            elower=(45, 55), nair=(55, 59), delta=(59, 67))


def parse_file(fn, want_mol):
    rows = []
    with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if len(line) < 67:
                continue
            try:
                mol = int(line[0:2])
                iso = int(line[2:3])
                if mol != want_mol:
                    continue
                rows.append([iso] + [float(line[a:b]) for a, b in COLS.values()])
            except ValueError:
                continue
    return np.array(rows, dtype=float) if rows else np.zeros((0, 8))


def main():
    for mol, M in MOLS.items():
        files = sorted(glob.glob(os.path.join(RAW, mol + '_*.par')))
        arrs = [parse_file(f, M) for f in files]
        arr = np.vstack([a for a in arrs if len(a)])
        n0 = len(arr)
        # de-duplicate boundary lines (iso, nu, sw)
        key = np.round(arr[:, [0, 1, 2]], 6)
        _, idx = np.unique(key, axis=0, return_index=True)
        arr = arr[np.sort(idx)]
        print('%s: %d files, %d lines (%d duplicates removed)'
              % (mol, len(files), len(arr), n0 - len(arr)), flush=True)
        print('  isotopologues:', dict(zip(*np.unique(arr[:, 0].astype(int),
                                                      return_counts=True))), flush=True)
        np.savez_compressed(os.path.join(OUT, mol + '.npz'),
                            iso=arr[:, 0].astype(np.int16),
                            nu=arr[:, 1], sw=arr[:, 2], gair=arr[:, 3],
                            gself=arr[:, 4], elower=arr[:, 5],
                            nair=arr[:, 6], delta=arr[:, 7])


if __name__ == '__main__':
    main()

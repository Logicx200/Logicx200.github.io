# -*- coding: utf-8 -*-
"""Download HITRAN2020 line data for H2O, CO2, CH4 over 475-5025 cm-1 in chunks."""
import time, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, r'F:\DeepSeek工作区\hitran_slant')
from dl_chunk import fetch

OUT = r'F:\DeepSeek工作区\hitran_slant\db_raw'
os.makedirs(OUT, exist_ok=True)
MOLS = ['H2O', 'CO2', 'CH4']
EDGES = list(range(475, 5026, 250))          # 475,725,...,4775,5025
jobs = [(m, a, a + 250) for m in MOLS for a in EDGES[:-1]]
# make the last chunk end exactly at 5025 (already does: 4775+250=5025)

print('jobs', len(jobs), flush=True)
t0 = time.time()
done = 0
with ThreadPoolExecutor(8) as ex:
    futs = {ex.submit(fetch, *j, OUT): j for j in jobs}
    for f in as_completed(futs):
        j = futs[f]
        fn, msg = f.result()
        done += 1
        print('[progress %d/%d] %s %s-%s: %s (%.0fs)'
              % (done, len(jobs), j[0], j[1], j[2], msg, time.time() - t0), flush=True)
print('TOTAL %.0fs' % (time.time() - t0))

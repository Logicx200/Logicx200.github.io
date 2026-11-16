# -*- coding: utf-8 -*-
"""Serially (re)download HITRAN2020 chunks with range verification.

The /lbl/api endpoint cross-contaminates concurrent queries, so this runs
one request at a time and validates that the returned wavenumbers stay
inside the requested window.
"""
import os, sys, time, glob
import requests

OUT = r'F:\DeepSeek工作区\hitran_slant\db_raw'
os.makedirs(OUT, exist_ok=True)
MOL_ISO = {
    'H2O': '1,2,3,4,5,6,129',
    'CO2': '7,8,9,10,11,12,13,14,121,15',
    'CH4': '32,33,34,35',
}
EDGES = list(range(475, 5026, 250))


def content_range(txt):
    nums = []
    for line in txt.splitlines():
        try:
            nums.append(float(line[3:15]))
        except Exception:
            pass
    if not nums:
        return None, 0
    return (min(nums), max(nums)), len(nums)


def get_chunk(mol, a, b, retries=6):
    url = 'https://hitran.org/lbl/api?iso_ids_list=%s&numin=%d&numax=%d' % (MOL_ISO[mol], a, b)
    last = 'no attempt'
    for k in range(retries):
        try:
            t = time.time()
            r = requests.get(url, timeout=900)
            if r.status_code != 200:
                last = 'HTTP %d' % r.status_code
            else:
                rng, n = content_range(r.text)
                if rng is not None and rng[0] >= a - 0.01 and rng[1] <= b + 0.01:
                    fn = os.path.join(OUT, '%s_%05d_%05d.par' % (mol, a, b))
                    tmp = fn + '.tmp'
                    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
                        f.write(r.text)
                    os.replace(tmp, fn)
                    return True, 'n=%d %.0fs' % (n, time.time() - t)
                last = 'bad range %s' % (rng,)
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, str(e)[:60])
        time.sleep(2 + 2 * k)
    return False, 'FAILED ' + last


def main():
    for f in glob.glob(os.path.join(OUT, '*.par')):
        os.remove(f)
    jobs = [(m, a, a + 250) for m in MOL_ISO for a in EDGES[:-1]]
    t0 = time.time()
    nfail = 0
    for i, (m, a, b) in enumerate(jobs, 1):
        ok, msg = get_chunk(m, a, b)
        nfail += 0 if ok else 1
        print('[progress %d/%d] %s %d-%d: %s%s (%.0fs)'
              % (i, len(jobs), m, a, b, msg, '' if ok else ' !!!', time.time() - t0), flush=True)
    print('TOTAL %.0fs, failures=%d' % (time.time() - t0, nfail))


if __name__ == '__main__':
    main()

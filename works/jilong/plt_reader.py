# -*- coding: utf-8 -*-
"""健壮的 MassFlow Tecplot 解析：逐帧提取，跳过非数据行。"""
import re
import sys
import numpy as np


def iter_zones(path, max_frames=None):
    zone_re = re.compile(r'i\s*=\s*(\d+)\s*,\s*j\s*=\s*(\d+)', re.I)
    t_re = re.compile(r'T\s*=\s*"([^"]+)"')
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        nx = ny = None
        t = None
        rows = []
        n = 0
        for line in f:
            up = line.lstrip().upper()
            if up.startswith('VARIABLES'):
                continue
            if up.startswith('ZONE'):
                if nx is not None and len(rows) == n and n > 0:
                    yield t, np.array(rows, dtype=np.float32).reshape(ny, nx, 10)
                    if max_frames and len(rows):
                        pass
                m = zone_re.search(line)
                tm = t_re.search(line)
                if not m:
                    nx = ny = None
                    continue
                nx, ny = int(m.group(1)), int(m.group(2))
                t = float(tm.group(1)) if tm else None
                rows = []
                n = nx * ny
                continue
            if nx is None:
                continue
            if len(rows) >= n:
                continue
            p = line.split()
            if len(p) < 10:
                continue
            try:
                rows.append([float(v) for v in p[:10]])
            except ValueError:
                continue
        if nx is not None and len(rows) == n and n > 0:
            yield t, np.array(rows, dtype=np.float32).reshape(ny, nx, 10)


def describe(path):
    for t, a in iter_zones(path):
        ny, nx, _ = a.shape
        H = a[:, :, 4]
        Hmax = a[:, :, 7]
        U = a[:, :, 5]
        V = a[:, :, 6]
        spd = np.sqrt(U ** 2 + V ** 2)
        wet = H > 0.05
        rr = np.where(wet.any(axis=1))[0]
        cc = np.where(wet.any(axis=0))[0]
        print('  t=%6.1f s  Hmax=%7.2f m  Vmax=%8.2f m/s  wet=%6d  '
              'rows %s  cols %s  vol=%.4e m3'
              % (t, H.max(), spd.max(), wet.sum(),
                 ('%d..%d' % (rr.min(), rr.max())) if rr.size else '--',
                 ('%d..%d' % (cc.min(), cc.max())) if cc.size else '--',
                 float(H.sum()) * 30 * 300))


if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else r'F:\DeepSeek工作区\jilong\mf_run2\output1_region1.plt'
    print('解析', p)
    describe(p)

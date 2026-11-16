# -*- coding: utf-8 -*-
"""
MassFlow Tecplot 输出解析器。
格式:
  VARIABLES ="X" "Y" "Surface" "Base" "H" "U" "V" "Hmax" "Hvmax" "Hvvmax"
  ZONE T="  0.000000" i=770,j=1166
  x y surface base H U V Hmax Hvmax Hvvmax   (X 变化最快, j 行)

设计为流式读取，避免把 500MB+ 文件整个载入内存。
"""
import numpy as np
import re

VARS = ['X', 'Y', 'Surface', 'Base', 'H', 'U', 'V', 'Hmax', 'Hvmax', 'Hvvmax']
NX = 770
NY = 1166


def iter_zones(path):
    """逐帧 yield (t, array[nx, ny, nvars])"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        while True:
            line = f.readline()
            if not line:
                return
            if line.upper().startswith('ZONE'):
                m = re.search(r'i\s*=\s*(\d+)\s*,\s*j\s*=\s*(\d+)', line, re.I)
                tm = re.search(r'T\s*=\s*"([^"]+)"', line)
                if not m:
                    continue
                nx, ny = int(m.group(1)), int(m.group(2))
                t = float(tm.group(1)) if tm else None
                n = nx * ny
                buf = np.empty((n, len(VARS)), dtype=np.float32)
                k = 0
                while k < n:
                    ln = f.readline()
                    if not ln:
                        break
                    parts = ln.split()
                    if len(parts) < len(VARS):
                        continue
                    buf[k] = [float(v) for v in parts[:len(VARS)]]
                    k += 1
                if k == n:
                    yield t, buf.reshape(ny, nx, len(VARS))
                else:
                    return


def make_xyz(a):
    return a[0, :, 0], a[:, 0, 1]


def stats(path, only_last=True):
    out = []
    for t, a in iter_zones(path):
        H = a[:, :, 4]
        Hmax = a[:, :, 7]
        wet = H > 0.05
        n_wet = int(wet.sum())
        area = n_wet * 900.0 / 1e6
        vol = float(H.sum()) * 900.0
        hs = float(H.max())
        vm = float(np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2).max())
        out.append(dict(t=t, wet_cells=n_wet, area_km2=area, vol_e6=vol / 1e6,
                        H_max=hs, V_max=vm))
        if only_last:
            pass
    return out


if __name__ == '__main__':
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else r'F:\DeepSeek工作区\jilong\mf_run\output1_region1.plt'
    print('解析:', p)
    for t, a in iter_zones(p):
        H = a[:, :, 4]
        Hmax = a[:, :, 7]
        V = np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2)
        wet = H > 0.05
        print('--- t = %.1f s ---' % (t if t is not None else -1))
        print('   形状 %s   H: max=%.2f m  sum=%.3e m3' % (a.shape, H.max(), H.sum() * 900))
        print('   Hmax: max=%.2f m' % Hmax.max())
        print('   |V| : max=%.2f m/s' % V.max())
        print('   湿区格数 %d (%.2f km2)' % (wet.sum(), wet.sum() * 900 / 1e6))
        if wet.any():
            rr, cc = np.where(wet)
            print('   范围 col %d..%d  row %d..%d' % (cc.min(), cc.max(), rr.min(), rr.max()))

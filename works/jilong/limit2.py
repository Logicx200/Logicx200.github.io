# -*- coding: utf-8 -*-
"""探测 demo 构建的网格上限精确位置，为提精度定网格。"""
import os
import re
import shutil
import subprocess
import sys
import numpy as np

SRC = r'D:\MassFlow\massflow\Bin\massflow'
BASE = r'F:\DeepSeek工作区\jilong\_lim2'


def w(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
        f.write('xllcorner     0.000000\nyllcorner     0.000000\n')
        f.write('cellsize      30.000000\nNODATA_value  %.1f\n' % nodata)
        for row in arr:
            f.write(' '.join('%.3f' % v for v in row) + '\n')


def test(nx, ny):
    d = os.path.join(BASE, '%dx%d' % (nx, ny))
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 5000.0 - yy * 10.0
    H = np.zeros((ny, nx)); H[3:9, 3:9] = 30.0
    w(os.path.join(d, 'z.txt'), Z, -9999.0)
    w(os.path.join(d, 'h.txt'), H, 0.0)
    with open(os.path.join(d, 'input.txt'), 'w', encoding='gbk') as f:
        f.write("""*nregions,1
*type,1
*erosion,0
*density,0
*grav_inertia,0
*ndim,2
*mbc,0
*remesh,0
*mpi,0
*omp,2
*limiter,1
*q1_flag,1
*solver,1
*create,grid,input,1,%d,%d,0.000000,0.000000,30.0,30.0
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.05,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,10,0.01,0.25
*output,1,tecplot,1,1,1,5
""" % (nx, ny))
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(SRC, f), os.path.join(d, f))
    try:
        p = subprocess.run([os.path.join(d, 'massflow.exe')], cwd=d,
                           capture_output=True, text=True, timeout=420,
                           encoding='gbk', errors='replace')
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', -1
    out = (p.stdout or '') + (p.stderr or '')
    if 'Computation is done' not in out:
        return 'FAIL', -1
    plt = os.path.join(d, 'output1_region1.plt')
    if not os.path.exists(plt):
        return 'NOOUT', -1
    vmax = 0.0
    with open(plt, encoding='utf-8', errors='replace') as f:
        cur = 0; tot = nx * ny
        for line in f:
            q = line.split()
            if len(q) >= 10 and q[0].replace('.', '').replace('-', '').isdigit():
                try:
                    u, v = float(q[5]), float(q[6])
                    vmax = max(vmax, (u * u + v * v) ** 0.5)
                except ValueError:
                    pass
    return ('OK' if vmax > 0.5 else 'FROZEN'), vmax


for nx, ny in [(633, 90), (633, 120), (633, 150), (633, 160), (633, 180),
               (800, 90), (1000, 90), (1200, 90)]:
    st, vm = test(nx, ny)
    print('%5dx%-5d = %8d 格  %-8s Vmax=%.2f' % (nx, ny, nx * ny, st, vm))
    sys.stdout.flush()

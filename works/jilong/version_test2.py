# -*- coding: utf-8 -*-
"""测试 Debug / Release 构建的网格上限。"""
import os
import shutil
import subprocess
import sys
import glob
import numpy as np

def find(pattern_dir):
    hits = glob.glob(pattern_dir, recursive=True)
    hits = [h for h in hits if h.lower().endswith('massflow.exe')]
    return os.path.dirname(hits[0]) if hits else None


VAR = {}
d = find(r'D:\MassFlow\massflow\计算案例\**\x64\Debug\massflow.exe')
r = find(r'D:\MassFlow\massflow\计算案例\**\x64\Release\massflow.exe')
if d: VAR['debug'] = d
if r: VAR['release'] = r
print('Debug  :', d)
print('Release:', r)
print()

BASE = r'F:\DeepSeek工作区\jilong\_ver_test'


def w(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     0.000000\nyllcorner     0.000000\n')
        f.write('cellsize      30.000000\nNODATA_value  %.1f\n' % nodata)
        for row in arr:
            f.write(' '.join('%.3f' % v for v in row) + '\n')


def build(nx, ny, d, vdir):
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 100.0 - yy * 0.5 + xx * 0.1
    H = np.zeros((ny, nx))
    H[ny // 3:ny // 3 + max(2, ny // 5), nx // 3:nx // 3 + max(2, nx // 5)] = 5.0
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
*omp,8
*limiter,1
*q1_flag,1
*solver,1
*create,grid,input,1,%d,%d,0.000000,0.000000,30.0,30.0
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,5000,0.45,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,5,0.01,0.25
*output,1,tecplot,1,1,1,5
""" % (nx, ny))
    for f in ('massflow.exe', 'solver.dll'):
        s = os.path.join(vdir, f)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(d, f))


for name, vdir in VAR.items():
    print('=== %s ===' % name)
    for nx, ny in [(300, 300), (250, 400), (400, 600), (770, 1166)]:
        dd = os.path.join(BASE, name, '%dx%d' % (nx, ny))
        build(nx, ny, dd, vdir)
        try:
            p = subprocess.run([os.path.join(dd, 'massflow.exe')], cwd=dd,
                               capture_output=True, text=True, timeout=400,
                               encoding='gbk', errors='replace')
        except subprocess.TimeoutExpired:
            print('  %4dx%-4d = %7d  TIMEOUT' % (nx, ny, nx * ny)); continue
        out = (p.stdout or '') + (p.stderr or '')
        ok = 'Computation is done' in out
        print('  %4dx%-4d = %7d  %s' % (nx, ny, nx * ny, 'OK' if ok else 'FAIL'))
        sys.stdout.flush()
    print()

# -*- coding: utf-8 -*-
"""
系统探测 demo / debug 构建在大网格下是否真的计算流动。
判据：不只是"跑完"，而是 20 s 后湿区扩展且速度非零。
"""
import os
import re
import shutil
import subprocess
import sys
import glob
import numpy as np

BASE = r'F:\DeepSeek工作区\jilong\_limit_test'
DEMO = r'D:\MassFlow\massflow\Bin\massflow'
_d = glob.glob(r'D:\MassFlow\massflow\计算案例\**\x64\Debug\massflow.exe', recursive=True)
DEBUG = os.path.dirname(_d[0]) if _d else None
print('DEMO :', DEMO)
print('DEBUG:', DEBUG)
print()


def w(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
        f.write('xllcorner     0.000000\nyllcorner     0.000000\n')
        f.write('cellsize      30.000000\nNODATA_value  %.1f\n' % nodata)
        for row in arr:
            f.write(' '.join('%.3f' % v for v in row) + '\n')


def build(nx, ny, d, vdir):
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 5000.0 - yy * 10.0
    H = np.zeros((ny, nx))
    H[5:15, 5:15] = 30.0
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
*omp,4
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
*time,1,20,0.01,0.25
*output,1,tecplot,1,1,1,10
""" % (nx, ny))
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(vdir, f), os.path.join(d, f))


def analyse(plt, nx):
    if not os.path.exists(plt):
        return None
    zones = []
    cur = None
    with open(plt, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            u = line.lstrip().upper()
            if u.startswith('VARIABLES'):
                continue
            if u.startswith('ZONE'):
                if cur:
                    zones.append(cur)
                tm = re.search(r'T\s*=\s*"([^"]+)"', line)
                cur = {'t': float(tm.group(1)) if tm else -1, 'rows': []}
            elif cur is not None and len(cur['rows']) < nx * 100000:
                p = line.split()
                if len(p) >= 10:
                    try:
                        cur['rows'].append([float(v) for v in p[:10]])
                    except ValueError:
                        pass
    if cur:
        zones.append(cur)
    if not zones:
        return None
    last = zones[-1]
    a = np.array(last['rows'])
    if a.size == 0:
        return None
    H = a[:, 4]
    spd = np.sqrt(a[:, 5] ** 2 + a[:, 6] ** 2)
    return dict(t=last['t'], Hmax=float(H.max()), Vmax=float(spd.max()),
                wet=int((H > 0.05).sum()), nframes=len(zones))


SIZES = [(400, 400), (600, 600), (800, 800), (1000, 1000), (1200, 1200)]
for name, vdir in [('DEMO', DEMO), ('DEBUG', DEBUG)]:
    if vdir is None:
        continue
    print('=== %s ===' % name)
    for nx, ny in SIZES:
        d = os.path.join(BASE, name, '%dx%d' % (nx, ny))
        build(nx, ny, d, vdir)
        nc = nx * ny
        try:
            p = subprocess.run([os.path.join(d, 'massflow.exe')], cwd=d,
                               capture_output=True, text=True, timeout=600,
                               encoding='gbk', errors='replace')
        except subprocess.TimeoutExpired:
            print('  %5dx%-5d (%9d 格) TIMEOUT' % (nx, ny, nc)); sys.stdout.flush(); continue
        ok = 'Computation is done' in (p.stdout or '')
        res = analyse(os.path.join(d, 'output1_region1.plt'), nx)
        if res and res['Vmax'] > 0.5:
            print('  %5dx%-5d (%9d 格) OK   Vmax=%8.2f  wet=%6d  帧=%d'
                  % (nx, ny, nc, res['Vmax'], res['wet'], res['nframes']))
        elif ok:
            print('  %5dx%-5d (%9d 格) FROZEN (Vmax=%.3f)' % (nx, ny, nc, res['Vmax'] if res else -1))
        else:
            print('  %5dx%-5d (%9d 格) FAIL' % (nx, ny, nc))
        sys.stdout.flush()
    print()

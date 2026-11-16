# -*- coding: utf-8 -*-
"""二分测试 MassFlow 能处理的最大网格规模。"""
import os
import shutil
import subprocess
import sys
import numpy as np

SRC = r'D:\MassFlow\massflow\计算案例\2.案例2白格滑坡\2.2基本操作\2.2.4已有建模文件时的命令流操作'
BASE = r'F:\DeepSeek工作区\jilong\_size_test'


def w(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     0.000000\n')
        f.write('yllcorner     0.000000\n')
        f.write('cellsize      30.000000\n')
        f.write('NODATA_value  %.1f\n' % nodata)
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % v for v in arr[r]) + '\n')


def build(nx, ny, d):
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 100.0 - yy * 0.5 + xx * 0.1
    H = np.zeros((ny, nx))
    hh = max(2, ny // 5)
    ww = max(2, nx // 5)
    H[ny // 3:ny // 3 + hh, nx // 3:nx // 3 + ww] = 5.0
    w(os.path.join(d, 'z.txt'), Z, -9999.0)
    w(os.path.join(d, 'h.txt'), H, 0.0)
    inp = """!计算区块数
*nregions,1
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
""" % (nx, ny)
    with open(os.path.join(d, 'input.txt'), 'w', encoding='gbk') as f:
        f.write(inp)
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(SRC, f), os.path.join(d, f))


def run(nx, ny):
    d = os.path.join(BASE, '%dx%d' % (nx, ny))
    ncells = nx * ny
    if ncells > 400000:
        print('  %4dx%-4d (%7d)  跳过: 过大' % (nx, ny, ncells))
        return None
    build(nx, ny, d)
    p = subprocess.run([os.path.join(d, 'massflow.exe')], cwd=d,
                       capture_output=True, text=True, timeout=300,
                       encoding='gbk', errors='replace')
    out = (p.stdout or '') + (p.stderr or '')
    ok = 'Computation is done' in out
    err = ''
    for ln in (p.stderr or '').splitlines():
        if 'severe' in ln or 'generatetxt' in ln:
            err = ln.strip(); break
    print('  %4dx%-4d (%7d 格)  %s  %s' % (
        nx, ny, ncells, 'OK ' if ok else 'FAIL', err if not ok else ''))
    return ok


print('=== 网格规模测试 ===')
for nx, ny in [(50, 50), (100, 100), (150, 150), (200, 200), (253, 239),
               (250, 250), (250, 400), (250, 600), (250, 1000),
               (300, 300), (400, 400), (512, 512)]:
    try:
        run(nx, ny)
    except subprocess.TimeoutExpired:
        print('  %4dx%-4d  超时' % (nx, ny))
    sys.stdout.flush()

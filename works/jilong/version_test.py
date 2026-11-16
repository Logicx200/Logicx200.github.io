# -*- coding: utf-8 -*-
"""测试不同构建版本的 massflow.exe 是否有更高网格上限。"""
import os
import shutil
import subprocess
import sys
import numpy as np

VARIANTS = {
    'demo_1.01MB': (r'D:\MassFlow\massflow\Bin\massflow',
                    'massflow.exe', 'solver.dll'),
    'release_1.02MB': (r'D:\MassFlow\massflow\计算案例\5.案例5不对称溃坝\5.2基本操作\5.2.5已有建模文件命令流操作\main\massflow\massflow\x64\Release',
                       'massflow.exe', 'solver.dll'),
    'debug_2.72MB': (r'D:\MassFlow\massflow\计算案例\5.案例5不对称溃坝\5.2基本操作\5.2.5已有建模文件命令流操作\main\massflow\massflow\x64\Debug',
                     'massflow.exe', 'solver.dll'),
}
BASE = r'F:\DeepSeek工作区\jilong\_ver_test'


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


def build(nx, ny, d, vdir, vexe, vdll):
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 100.0 - yy * 0.5 + xx * 0.1
    H = np.zeros((ny, nx))
    H[ny // 3:ny // 3 + max(2, ny // 5), nx // 3:nx // 3 + max(2, nx // 5)] = 5.0
    w(os.path.join(d, 'z.txt'), Z, -9999.0)
    w(os.path.join(d, 'h.txt'), H, 0.0)
    inp = """*nregions,1
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
    for f in (vexe, vdll):
        src = os.path.join(vdir, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(d, f))
        else:
            print('    缺少 %s' % src)


def test(vname, vdir, vexe, vdll, sizes):
    print('=== %s ===' % vname)
    print('  目录: %s' % vdir)
    if not os.path.exists(os.path.join(vdir, vexe)):
        print('  exe 不存在，跳过'); return
    for nx, ny in sizes:
        d = os.path.join(BASE, vname.replace('.', '_'), '%dx%d' % (nx, ny))
        build(nx, ny, d, vdir, vexe, vdll)
        try:
            p = subprocess.run([os.path.join(d, vexe)], cwd=d,
                               capture_output=True, text=True, timeout=300,
                               encoding='gbk', errors='replace')
        except subprocess.TimeoutExpired:
            print('  %4dx%-4d = %7d 格  TIMEOUT' % (nx, ny, nx * ny)); continue
        out = (p.stdout or '') + (p.stderr or '')
        ok = 'Computation is done' in out
        print('  %4dx%-4d = %7d 格  %s' % (nx, ny, nx * ny, 'OK' if ok else 'FAIL'))
        sys.stdout.flush()


SIZES = [(250, 400), (300, 300), (400, 600), (500, 700), (770, 1166)]
for vname, (vdir, vexe, vdll) in VARIANTS.items():
    test(vname, vdir, vexe, vdll, SIZES)
    print()

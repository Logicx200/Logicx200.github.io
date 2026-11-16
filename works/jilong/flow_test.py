# -*- coding: utf-8 -*-
"""
对照测试：同一个公式的输入，分别用 demo 构建和 debug 构建跑，
检查流体是否真的运动。用简单倾坡，排除地形因素。
"""
import os
import shutil
import subprocess
import sys
import numpy as np

BASE = r'F:\DeepSeek工作区\jilong\_flow_test'
DEMO = r'D:\MassFlow\massflow\Bin\massflow'
import glob
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
    # 向北(行号小)高、向南低 => 沿 +row 方向下坡
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    Z = 5000.0 - yy * 10.0          # 每格降 10 m => 坡度 33%
    H = np.zeros((ny, nx))
    H[10:20, 10:20] = 30.0          # 30 m 厚冰块
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
*material,1,friction,1,0,0.15,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,20,0.01,0.25
*output,1,tecplot,1,1,1,5
""" % (nx, ny))
    for f in ('massflow.exe', 'solver.dll'):
        s = os.path.join(vdir, f)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(d, f))


def summarize(plt, tag):
    if not os.path.exists(plt):
        print('   [%s] 无输出文件' % tag); return
    with open(plt, 'r', encoding='utf-8', errors='replace') as f:
        zones = []
        cur = None
        for line in f:
            if line.upper().startswith('ZONE'):
                if cur is not None:
                    zones.append(cur)
                import re
                tm = re.search(r'T\s*=\s*"([^"]+)"', line)
                cur = {'t': float(tm.group(1)) if tm else -1, 'rows': []}
            elif cur is not None and len(cur['rows']) < 200000:
                p = line.split()
                if len(p) >= 10:
                    try:
                        cur['rows'].append([float(v) for v in p[:10]])
                    except ValueError:
                        pass
        if cur is not None:
            zones.append(cur)
    print('   [%s] 共 %d 帧' % (tag, len(zones)))
    for z in zones[:4] + zones[-1:]:
        a = np.array(z['rows'])
        if a.size == 0:
            continue
        H = a[:, 4]; U = a[:, 5]; V = a[:, 6]
        spd = np.sqrt(U ** 2 + V ** 2)
        print('      t=%5.1f  Hmax=%7.2f  Vmax=%8.3f  wet=%6d  体积=%.4e'
              % (z['t'], H.max(), spd.max(), (H > 0.05).sum(), H.sum() * 900))


for name, vdir in [('DEMO', DEMO), ('DEBUG', DEBUG)]:
    if vdir is None:
        continue
    d = os.path.join(BASE, name)
    build(60, 60, d, vdir)
    try:
        subprocess.run([os.path.join(d, 'massflow.exe')], cwd=d,
                       capture_output=True, text=True, timeout=180,
                       encoding='gbk', errors='replace')
    except subprocess.TimeoutExpired:
        print('%s 超时' % name)
    print('=== %s ===' % name)
    summarize(os.path.join(d, 'output1_region1.plt'), name)
    print()

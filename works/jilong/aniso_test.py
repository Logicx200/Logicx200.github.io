# -*- coding: utf-8 -*-
"""
测试 MassFlow 是否支持各向异性网格 (dx != dy)。
若支持，就能用 30m 横向 + 300m 纵向 覆盖 23x35km 而总格数 < 10 万。
对照组：等向网格，相同格数与相同坡度。
"""
import os
import re
import shutil
import subprocess
import numpy as np

BASE = r'F:\DeepSeek工作区\jilong\_aniso_test'
DEMO = r'D:\MassFlow\massflow\Bin\massflow'
os.makedirs(BASE, exist_ok=True)


def w(p, arr, nodata, cs, xll=0.0, yll=0.0):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
        f.write('xllcorner     %.6f\nyllcorner     %.6f\n' % (xll, yll))
        f.write('cellsize      %.6f\nNODATA_value  %.1f\n' % (cs, nodata))
        for row in arr:
            f.write(' '.join('%.3f' % v for v in row) + '\n')


def build(nx, ny, dx, dy, d, slope=0.30):
    os.makedirs(d, exist_ok=True)
    xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
    # 行号增大 = 向南 = 降低; 每格降 slope*dy
    Z = 5000.0 - yy * (slope * dy)
    H = np.zeros((ny, nx))
    H[10:30, 10:60] = 40.0
    # 注意: MassFlow 的 z.txt/h.txt 只有一个 cellsize 头字段，
    # 真实间距由 input.txt 的 *create,grid 决定
    w(os.path.join(d, 'z.txt'), Z, -9999.0, min(dx, dy))
    w(os.path.join(d, 'h.txt'), H, 0.0, min(dx, dy))
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
*create,grid,input,1,%d,%d,0.000000,0.000000,%.1f,%.1f
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,0,0.15,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,30,0.01,0.25
*output,1,tecplot,1,1,1,10
""" % (nx, ny, dx, dy))


def run_case(tag, nx, ny, dx, dy):
    d = os.path.join(BASE, tag)
    build(nx, ny, dx, dy, d)
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(DEMO, f), os.path.join(d, f))
    print('=== %s  nx=%d ny=%d dx=%.1f dy=%.1f  (%.0f x %.0f m, %d 格) ==='
          % (tag, nx, ny, dx, dy, nx * dx, ny * dy, nx * ny))
    try:
        subprocess.run([os.path.join(d, 'massflow.exe')], cwd=d,
                       capture_output=True, text=True, timeout=300,
                       encoding='gbk', errors='replace')
    except subprocess.TimeoutExpired:
        print('   超时'); return
    plt = os.path.join(d, 'output1_region1.plt')
    if not os.path.exists(plt):
        print('   无输出'); return
    zones = []
    cur = None
    with open(plt, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.upper().startswith('ZONE'):
                if cur: zones.append(cur)
                tm = re.search(r'T\s*=\s*"([^"]+)"', line)
                cur = {'t': float(tm.group(1)) if tm else -1, 'rows': []}
            elif cur is not None and len(cur['rows']) < 400000:
                p = line.split()
                if len(p) >= 10:
                    try: cur['rows'].append([float(v) for v in p[:10]])
                    except ValueError: pass
    if cur: zones.append(cur)
    print('   帧数 %d' % len(zones))
    for z in [zones[0], zones[len(zones) // 2], zones[-1]]:
        a = np.array(z['rows'])
        if a.size == 0: continue
        H = a[:, 4]
        spd = np.sqrt(a[:, 5] ** 2 + a[:, 6] ** 2)
        # 沿程前缘位置: 湿区最大列坐标(向南)
        wet = H > 0.05
        # 列优先展开: X 变化最快 => 重塑
        ny_ = len(H) // nx
        try:
            H2 = H.reshape(ny_, nx)
            w2 = H2 > 0.05
            front_row = int(np.where(w2.any(axis=1))[0].max()) if w2.any() else -1
        except Exception:
            front_row = -1
        print('   t=%5.1f  Hmax=%7.2f  Vmax=%8.3f  wet=%6d  前缘行=%d (%.0f m)  体积=%.4e'
              % (z['t'], H.max(), spd.max(), wet.sum(), front_row,
                 front_row * dy if front_row >= 0 else 0, H.sum() * dx * dy))
    print()


# 等向对照组
run_case('iso_30m', 320, 312, 30.0, 30.0)
# 各向异性：横向 30m，纵向 300m
run_case('aniso_30x300', 320, 312, 30.0, 300.0)
# 各向异性：横向 30m，纵向 120m
run_case('aniso_30x120', 320, 312, 30.0, 120.0)

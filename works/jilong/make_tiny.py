# -*- coding: utf-8 -*-
"""生成 50x50 极小测试工程，用于隔离 MassFlow 输入格式问题。"""
import os
import numpy as np

T = r'F:\DeepSeek工作区\jilong\_test_tiny'
os.makedirs(T, exist_ok=True)

nx, ny, cs = 50, 50, 30.0
xll, yll = 0.0, 0.0

# 简单斜面 + 一个小方块水体
xx, yy = np.meshgrid(np.arange(nx), np.arange(ny))
Z = 100.0 - yy * 0.5 + xx * 0.1
H = np.zeros((ny, nx))
H[20:30, 20:30] = 5.0


def w(p, arr, nodata):
    with open(p, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     %.6f\n' % xll)
        f.write('yllcorner     %.6f\n' % yll)
        f.write('cellsize      %.6f\n' % cs)
        f.write('NODATA_value  %.1f\n' % nodata)
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % v for v in arr[r]) + '\n')


w(os.path.join(T, 'z.txt'), Z, -9999.0)
w(os.path.join(T, 'h.txt'), H, 0.0)

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
*create,grid,input,1,{nx},{ny},{xll:.6f},{yll:.6f},{cs:.1f},{cs:.1f}
*create,topo,file,dem,1,z.txt
*create,h,file,dem,1,h.txt
*create,bound,custom,1
*material,1,density,2000
*material,1,friction,1,5000,0.45,0
*material,1,earthpress,0.65,0.4228
*material_assign,1,0,1
*time,1,20,0.01,0.25
*output,1,tecplot,1,1,1,5
""".format(nx=nx, ny=ny, xll=xll, yll=yll, cs=cs)
with open(os.path.join(T, 'input.txt'), 'w', encoding='gbk') as f:
    f.write(inp)

import shutil
src = r'D:\MassFlow\massflow\计算案例\2.案例2白格滑坡\2.2基本操作\2.2.4已有建模文件时的命令流操作'
for f in ('massflow.exe', 'solver.dll'):
    shutil.copy2(os.path.join(src, f), os.path.join(T, f))
print('已生成', T)

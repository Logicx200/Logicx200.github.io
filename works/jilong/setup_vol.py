# -*- coding: utf-8 -*-
"""
体积标定：真实事件的"链式放大"意味着物质沿途增大。
用固定体积的模型近似它，需要更大的初始体积。
测试 V0 = 50 / 100 / 140 e6 m3，mu=0.005，T=1200 s。
"""
import os
import json
import shutil
import numpy as np

B = r'F:\DeepSeek工作区\jilong'
SRC = os.path.join(B, 'mf_long')
OUT = os.path.join(B, 'mf_vol')
os.makedirs(OUT, exist_ok=True)

import sys
sys.path.insert(0, B)
meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
DX, DY = meta['DX'], meta['DY']
NX, NY = meta['NX'], meta['NY']
E0, N0 = meta['E0'], meta['N0']
sc, sr = meta['src_col'], meta['src_row']
lc, lr = meta['lake_col'], meta['lake_row']
W_ = 980.0
L_ = 780.0
ang = np.arctan2(lr - sr, lc - sc)
yy, xx = np.mgrid[0:NY, 0:NX]
u = (xx - sc) * DX * np.cos(ang) + (yy - sr) * DY * np.sin(ang)
v = -(xx - sc) * DX * np.sin(ang) + (yy - sr) * DY * np.cos(ang)
a, b = L_ / 2.0, W_ / 2.0
shape = np.where((np.abs(u) <= a) & (np.abs(v) <= b),
                 np.clip(1 - (u / a) ** 2, 0, None) ** 0.5 * np.exp(-(v / (b * 0.55)) ** 2), 0.0)


def write_ascii(path, arr, nodata):
    with open(path, 'w', encoding='ascii') as f:
        f.write('ncols         %d\nnrows         %d\n' % (arr.shape[1], arr.shape[0]))
        f.write('xllcorner     %.6f\nyllcorner     %.6f\n' % (E0, N0))
        f.write('cellsize      %.6f\nNODATA_value  %.1f\n' % (min(DX, DY), nodata))
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % x for x in arr[r]) + '\n')


inp0 = open(os.path.join(SRC, 'input.txt'), encoding='gbk').read()
for V in (50e6, 100e6, 140e6):
    tag = 'v%03d' % round(V / 1e6)
    d = os.path.join(OUT, tag)
    os.makedirs(d, exist_ok=True)
    H = shape * (V / (shape.sum() * DX * DY))
    write_ascii(os.path.join(d, 'h.txt'), H, 0.0)
    shutil.copy2(os.path.join(SRC, 'z.txt'), os.path.join(d, 'z.txt'))
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(B, 'mf_long', f), os.path.join(d, f))
    inp = inp0.replace('*output,1,tecplot,1,1,1,60', '*output,1,tecplot,1,1,1,120')
    open(os.path.join(d, 'input.txt'), 'w', encoding='gbk').write(inp)
    for f in ('output1_region1.plt', 'stdout.log'):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    print('%-7s V0=%.0f e6 m3  最大厚 %.1f m  面积 %.3f km2'
          % (tag, V / 1e6, H.max(), (H > 0).sum() * DX * DY / 1e6))

# -*- coding: utf-8 -*-
"""用真实网格扫低 mu，找使 400 s 前缘抵达口岸(col 97) 的值。"""
import os
import shutil

SRC = r'F:\DeepSeek工作区\jilong\mf_real'
CAL = r'F:\DeepSeek工作区\jilong\mf_real_cal'
os.makedirs(CAL, exist_ok=True)
inp0 = open(os.path.join(SRC, 'input.txt'), encoding='gbk').read()

for mu in (0.02, 0.01, 0.005):
    tag = 'mu_%04d' % round(mu * 10000)
    d = os.path.join(CAL, tag)
    os.makedirs(d, exist_ok=True)
    for f in ('z.txt', 'h.txt', 'massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(SRC, f), os.path.join(d, f))
    t = inp0.replace('*material,1,friction,1,0,0.05,0',
                     '*material,1,friction,1,0,%g,0' % mu)
    t = t.replace('*omp,8', '*omp,2')
    t = t.replace('*output,1,tecplot,1,1,1,20', '*output,1,tecplot,1,1,1,50')
    open(os.path.join(d, 'input.txt'), 'w', encoding='gbk').write(t)
    for f in ('output1_region1.plt', 'stdout.log', '_status.txt'):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    print('已建 %s  mu=%g' % (d, mu))

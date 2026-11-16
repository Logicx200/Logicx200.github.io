# -*- coding: utf-8 -*-
"""
摩擦系数标定：用较低 mu 并行跑多组，找出使 400 s 前缘抵达口岸
(24.62 km) 的值。
场景目录 mf_cal/mu_XXX；输出间隔 80 s 以控制文件体积。
"""
import os
import json
import shutil
import subprocess
import sys
import numpy as np

BASE = r'F:\DeepSeek工作区\jilong'
SRC = os.path.join(BASE, 'mf_run2')
CAL = os.path.join(BASE, 'mf_cal')
DEMO = r'D:\MassFlow\massflow\Bin\massflow'
os.makedirs(CAL, exist_ok=True)

MUS = [0.08, 0.05, 0.03, 0.02]
OUT_INTERVAL = 80

inp0 = open(os.path.join(SRC, 'input.txt'), encoding='gbk').read()

made = []
for mu in MUS:
    tag = 'mu_%03d' % round(mu * 1000)
    d = os.path.join(CAL, tag)
    os.makedirs(d, exist_ok=True)
    for f in ('z.txt', 'h.txt'):
        shutil.copy2(os.path.join(SRC, f), os.path.join(d, f))
    for f in ('massflow.exe', 'solver.dll'):
        shutil.copy2(os.path.join(DEMO, f), os.path.join(d, f))
    txt = inp0.replace('*material,1,friction,1,0,0.15,0',
                       '*material,1,friction,1,0,%g,0' % mu)
    txt = txt.replace('*output,1,tecplot,1,1,1,20',
                      '*output,1,tecplot,1,1,1,%d' % OUT_INTERVAL)
    open(os.path.join(d, 'input.txt'), 'w', encoding='gbk').write(txt)
    made.append((mu, d))
    print('已建 %s  mu=%g' % (d, mu))

print()
print('全部就绪，共 %d 组' % len(made))

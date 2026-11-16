# -*- coding: utf-8 -*-
"""延长模拟时间到 1200 s，检验低摩擦算例最终能否抵达口岸。"""
import os
import shutil

SRC = r'F:\DeepSeek工作区\jilong\mf_real_cal\mu_0050'
DST = r'F:\DeepSeek工作区\jilong\mf_long'
os.makedirs(DST, exist_ok=True)
for f in ('z.txt', 'h.txt', 'massflow.exe', 'solver.dll'):
    shutil.copy2(os.path.join(SRC, f), os.path.join(DST, f))

inp = open(os.path.join(SRC, 'input.txt'), encoding='gbk').read()
inp = inp.replace('*time,1,400,0.01,0.25', '*time,1,1200,0.01,0.25')
inp = inp.replace('*output,1,tecplot,1,1,1,50', '*output,1,tecplot,1,1,1,60')
open(os.path.join(DST, 'input.txt'), 'w', encoding='gbk').write(inp)

for f in ('output1_region1.plt', 'stdout.log', 'cmd.txt', '_status.txt'):
    p = os.path.join(DST, f)
    if os.path.exists(p):
        os.remove(p)
print('已建', DST)
for l in inp.split('\n'):
    if l.startswith('*time') or l.startswith('*output') or l.startswith('*material,1,friction'):
        print('  ', l)

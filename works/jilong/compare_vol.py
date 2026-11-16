# -*- coding: utf-8 -*-
"""对比不同初始体积的抵达口岸时间与最终停止位置。"""
import os
import sys
import json
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

B = r'F:\DeepSeek工作区\jilong'
meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
DX = meta['DX']
sc, pc, pr = int(round(meta['src_col'])), int(round(meta['port_col'])), int(round(meta['port_row']))
print('源区 col%d  口岸 col%d  相距 %.2f km' % (sc, pc, (sc - pc) * DX / 1000))
print('观测: 400 s 抵达口岸')
print()

RUNS = [('V=50e6', os.path.join(B, 'mf_vol', 'v050', 'output1_region1.plt')),
        ('V=70e6', os.path.join(B, 'mf_long', 'output1_region1.plt')),
        ('V=100e6', os.path.join(B, 'mf_vol', 'v100', 'output1_region1.plt')),
        ('V=140e6', os.path.join(B, 'mf_vol', 'v140', 'output1_region1.plt'))]
print('%-9s %12s %14s %14s' % ('体积', '抵达口岸(s)', '1200s最终(km)', '超冲(km)'))
for lab, p in RUNS:
    if not os.path.exists(p):
        print('%-9s 无输出' % lab); continue
    first = None
    last_km = 0
    for t, a in iter_zones(p):
        H = a[:, :, 4]
        wet = H > 0.05
        cc = np.where(wet.any(axis=0))[0]
        front = int(cc.min()) if cc.size else 10 ** 6
        km = (sc - front) * DX / 1000
        last_km = max(last_km, km)
        hit = wet[max(0, pr - 4):pr + 5, max(0, pc - 6):pc + 7].any()
        if hit and first is None:
            first = t
    over = last_km - (sc - pc) * DX / 1000
    print('%-9s %12s %14.2f %14.2f'
          % (lab, ('%.0f' % first) if first else '未到达', last_km, over))

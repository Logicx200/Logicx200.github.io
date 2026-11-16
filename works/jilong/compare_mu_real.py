# -*- coding: utf-8 -*-
"""对比真实网格上不同 mu 的抵达口岸时间，找出匹配观测(400 s)的最优值。"""
import os
import sys
import json
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

B = r'F:\DeepSeek工作区\jilong'
meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
DX, DY = meta['DX'], meta['DY']
pc, pr = int(round(meta['port_col'])), int(round(meta['port_row']))
sc, sr = int(round(meta['src_col'])), int(round(meta['src_row']))
lc, lr = int(round(meta['lake_col'])), int(round(meta['lake_row']))
print('源区 col%d row%d | 堰塞湖 col%d row%d | 口岸 col%d row%d' % (sc, sr, lc, lr, pc, pr))
print('观测: 400 s 抵达口岸')
print()

RUNS = [('mu=0.05', os.path.join(B, 'mf_real', 'output1_region1.plt')),
        ('mu=0.02', os.path.join(B, 'mf_real_cal', 'mu_0200', 'output1_region1.plt')),
        ('mu=0.01', os.path.join(B, 'mf_real_cal', 'mu_0100', 'output1_region1.plt')),
        ('mu=0.005', os.path.join(B, 'mf_real_cal', 'mu_0050', 'output1_region1.plt'))]

summary = []
for lab, p in RUNS:
    if not os.path.exists(p):
        print('%-9s 无输出' % lab); continue
    recs = []
    for t, a in iter_zones(p):
        H = a[:, :, 4]
        spd = np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2)
        wet = H > 0.05
        cc = np.where(wet.any(axis=0))[0]
        front = int(cc.min()) if cc.size else 10 ** 6
        pw = wet[max(0, pr - 4):pr + 5, max(0, pc - 6):pc + 7]
        hp = float(H[max(0, pr - 4):pr + 5, max(0, pc - 6):pc + 7].max())
        recs.append(dict(t=t, front=front, port=bool(pw.any()), hport=hp,
                         Vmax=float(spd.max()), Hmax=float(H.max()),
                         run_km=(sc - front) * DX / 1000.0))
    tp = next((r['t'] for r in recs if r['port']), None)
    t_end = recs[-1]['t'] if recs else 0
    r_end = recs[-1]['run_km'] if recs else 0
    summary.append((lab, tp, t_end, r_end, recs))
    print('=== %s ===' % lab)
    for r in recs:
        print('   t=%6.1f  前缘col%4d  跑出 %5.2f km  Vmax=%6.1f  Hmax=%5.1f  厚度@口岸=%5.1f  %s'
              % (r['t'], r['front'], r['run_km'], r['Vmax'], r['Hmax'], r['hport'],
                 '**到口岸**' if r['port'] else ''))
    print('   -> 抵达口岸: %s' % ('%.0f s' % tp if tp else '未到达(400s时跑出 %.2f km)' % r_end))
    print()

print('=' * 60)
print('%-9s %12s %14s' % ('mu', '抵达口岸(s)', '400s跑出(km)'))
for lab, tp, te, re_, _ in summary:
    print('%-9s %12s %14.2f' % (lab, ('%.0f' % tp) if tp else '未到达', re_))
print()
print('观测: 400 s 抵达口岸（源区->口岸沿程约 17 km）')

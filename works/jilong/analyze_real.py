# -*- coding: utf-8 -*-
"""
修正模型结果分析：前缘抵达口岸/堰塞湖的时间，与观测对比。
"""
import os
import sys
import json
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

RUN = r'F:\DeepSeek工作区\jilong\mf_real'
meta = json.load(open(os.path.join(RUN, 'meta.json')))
DX, DY = meta['DX'], meta['DY']
pc, pr = int(round(meta['port_col'])), int(round(meta['port_row']))
lc, lr = int(round(meta['lake_col'])), int(round(meta['lake_row']))
sc, sr = int(round(meta['src_col'])), int(round(meta['src_row']))

print('源区 col%d row%d   堰塞湖 col%d row%d   口岸 col%d row%d' % (sc, sr, lc, lr, pc, pr))
print('源区->口岸 沿程约 %.2f km' % (np.hypot((pc - sc) * DX, (pr - sr) * DY) / 1000))
print('观测: 400 s 抵达口岸')
print()
print('%8s %8s %8s %8s %8s %6s %6s %6s %12s' % (
    't(s)', 'Hmax', 'Vmax', 'wet', '前缘col', '到湖', '到岸', '厚度@岸', '体积'))
recs = []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    U = a[:, :, 5]
    V = a[:, :, 6]
    spd = np.sqrt(U ** 2 + V ** 2)
    wet = H > 0.05
    cc = np.where(wet.any(axis=0))[0]
    front = int(cc.min()) if cc.size else -1
    lake_hit = bool(wet[lr, max(0, lc - 8):lc + 9].any())
    # 口岸周边 8 格的湿区
    port_win = wet[max(0, pr - 3):pr + 4, max(0, pc - 8):pc + 9]
    port_hit = bool(port_win.any())
    vol = float(H.sum()) * DX * DY
    hport = float(H[max(0, pr - 3):pr + 4, max(0, pc - 8):pc + 9].max())
    recs.append(dict(t=t, Hmax=float(H.max()), Vmax=float(spd.max()),
                     wet=int(wet.sum()), front=front, lake=lake_hit,
                     port=port_hit, hport=hport, vol=vol))
    print('%8.1f %8.1f %8.1f %8d %8d %6s %6s %6.1f %12.4e' % (
        t, H.max(), spd.max(), wet.sum(), front,
        'Y' if lake_hit else '-', 'Y' if port_hit else '-', hport, vol))

json.dump(recs, open(os.path.join(RUN, '..', 'results', 'real_front.json'), 'w'), indent=2)

print()
print('=== 关键结论 ===')
tl = next((r['t'] for r in recs if r['lake']), None)
tp = next((r['t'] for r in recs if r['port']), None)
print('抵达堰塞湖: %s s' % ('%.0f' % tl if tl else '未到达'))
print('抵达口岸  : %s s   (观测 400 s)' % ('%.0f' % tp if tp else '未到达'))
if recs:
    v0 = recs[0]['vol']
    v1 = recs[-1]['vol']
    print('体积守恒  : %.6e -> %.6e  (相对误差 %.2e)' % (v0, v1, abs(v1 - v0) / v0))
    print('末态最大厚度 %.1f m, 最大流速 %.1f m/s' % (recs[-1]['Hmax'], max(r['Vmax'] for r in recs)))

# -*- coding: utf-8 -*-
"""
提取 MassFlow 结果的关键量：
 - 各时刻前缘位置（距源区的沿程距离）
 - 体积守恒检查
 - 最大堆积厚度 / 最大流速
并输出标定曲线：前缘距离 vs 时间。
"""
import os
import sys
import json
import numpy as np
from plt_reader import iter_zones

RUN = r'F:\DeepSeek工作区\jilong\mf_run2'
OUT = r'F:\DeepSeek工作区\jilong\results'
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(RUN, 'meta.json')))
DX, DY = meta['DX'], meta['DY']
NX, NY = meta['NX'], meta['NY']
E0, N0 = meta['E0'], meta['N0']
src_r = meta['src_row']

# 口岸/核心受灾点 在网格中的位置
PORT_E, PORT_N = 340873.0, 3129127.0
port_c = (PORT_E - E0) / DX
port_r = (meta['N1'] - PORT_N) / DY
print('口岸/受灾点 -> col %.1f  row %.1f' % (port_c, port_r))
print('源区        -> col %.1f  row %.1f' % (meta['src_col'], src_r))
print()

recs = []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    U = a[:, :, 5]
    V = a[:, :, 6]
    spd = np.sqrt(U ** 2 + V ** 2)
    wet = H > 0.05
    vol = float(H.sum()) * DX * DY
    if wet.any():
        rr = np.where(wet.any(axis=1))[0]
        cc = np.where(wet.any(axis=0))[0]
        # 前缘：离源区最远的湿区像元（沿程 = 行号差）
        front_r = int(rr.max())
        front_d = (front_r - src_r) * DY / 1000.0
        # 受灾点是否已到达
        hit = bool(wet[int(round(port_r)), int(round(port_c))])
    else:
        rr = cc = [0]
        front_r = -1; front_d = 0.0; hit = False
    recs.append(dict(t=t, Hmax=float(H.max()), Vmax=float(spd.max()),
                     wet=int(wet.sum()), vol=vol,
                     front_row=front_r, front_km=front_d,
                     row_max=int(rr.max()), col_min=int(cc.min()), col_max=int(cc.max()),
                     port_hit=hit))
    print('t=%6.1f  Hmax=%6.1f  Vmax=%7.1f  wet=%5d  前缘 %.2f km (row %d)  体积 %.4e  %s'
          % (t, recs[-1]['Hmax'], recs[-1]['Vmax'], recs[-1]['wet'],
             front_d, front_r, vol, '<< 已到达口岸' if hit else ''))

json.dump(recs, open(os.path.join(OUT, 'front_curve.json'), 'w'), indent=2)
np.save(os.path.join(OUT, 'front_curve.npy'), np.array(
    [[r['t'], r['front_km'], r['Vmax'], r['Hmax'], r['wet'], r['vol']] for r in recs]))

print()
print('=== 标定关键信息 ===')
tot_km = (port_r - src_r) * DY / 1000.0
print('源区 -> 口岸 沿程距离 = %.2f km' % tot_km)
print('观测: 400 s 抵达口岸 (文献)')
if recs:
    last = recs[-1]
    print('本次 (mu=0.15): t=%.0f s 时前缘 %.2f km，占全程 %.1f%%'
          % (last['t'], last['front_km'], 100 * last['front_km'] / tot_km))
    v0 = recs[0]['vol']
    print('体积守恒: 初始 %.6e -> 末态 %.6e  (相对误差 %.3e)'
          % (v0, last['vol'], abs(last['vol'] - v0) / v0))

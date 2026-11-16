# -*- coding: utf-8 -*-
"""
读取各 mu 场景的输出（含进行中的部分结果），提取前缘曲线并比较，
找出使 400 s 前缘抵达口岸 (24.62 km) 的 mu。
"""
import os
import re
import glob
import json
import sys
import numpy as np
from plt_reader import iter_zones

BASE = r'F:\DeepSeek工作区\jilong'
CAL = os.path.join(BASE, 'mf_cal')
OUT = os.path.join(BASE, 'results')
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(os.path.join(BASE, 'mf_run2', 'meta.json')))
DX, DY = meta['DX'], meta['DY']
src_r = meta['src_row']
PORT_E, PORT_N = 340873.0, 3129127.0
port_r = (meta['N1'] - PORT_N) / DY
port_c = (PORT_E - meta['E0']) / DX
TARGET_KM = (port_r - src_r) * DY / 1000.0
TARGET_T = 400.0

print('目标: %.2f s 时前缘抵达 %.2f km (口岸)' % (TARGET_T, TARGET_KM))
print()

rows = []
for d in sorted(glob.glob(os.path.join(CAL, 'mu_*'))):
    tag = os.path.basename(d)
    m = re.search(r'mu_(\d+)', tag)
    mu = int(m.group(1)) / 1000.0 if m else None
    plots = sorted(glob.glob(os.path.join(d, 'output*.plt')))
    if not plots:
        print('%-8s 无输出' % tag); continue
    p = plots[0]
    rec = []
    try:
        for t, a in iter_zones(p):
            H = a[:, :, 4]
            wet = H > 0.05
            if wet.any():
                rr = np.where(wet.any(axis=1))[0]
                front = (int(rr.max()) - src_r) * DY / 1000.0
            else:
                front = 0.0
            rec.append((t, front, float(H.max())))
    except Exception as e:
        print('%-8s 解析中断 (%s)，已得 %d 帧' % (tag, e, len(rec)))
    if not rec:
        continue
    t400 = rec[-1]
    # 线性外推到 400 s
    est = None
    if len(rec) >= 2 and t400[0] > 1:
        k = t400[1] / t400[0]
        est = k * TARGET_T
    rows.append(dict(tag=tag, mu=mu, nframes=len(rec), t_last=t400[0],
                     front_last=t400[1], est_400=est, Hmax=t400[2]))
    print('%-8s mu=%-5s 帧数=%2d  t_last=%6.1f s  前缘=%6.2f km  (%.1f%%)  线性外推 400s=%.2f km  %s'
          % (tag, mu, len(rec), t400[0], t400[1], 100 * t400[1] / TARGET_KM,
             est if est is not None else -1,
             '<= 命中' if est and abs(est - TARGET_KM) < 2.5 else ''))

print()
print('=== 按 400s 外推前缘排序 ===')
for r in sorted(rows, key=lambda x: -(x['est_400'] or 0)):
    print('  mu=%-5s 外推 %.2f km  (目标 %.2f)' % (r['mu'], r['est_400'] or 0, TARGET_KM))

json.dump(rows, open(os.path.join(OUT, 'calibration.json'), 'w'), indent=2)

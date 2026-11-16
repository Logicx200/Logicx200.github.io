# -*- coding: utf-8 -*-
"""
分辨率收敛性分析：比较 20/30/40 m 横向格距下的前缘抵达时间。
若差异随加密而减小，说明趋于收敛。
"""
import os
import sys
import json
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones
from chanlib import build_channel, make_s_map

B = r'F:\DeepSeek工作区\jilong'
CASES = [
    ('20 m (基准)', 'mf_hi', 20.0, 140.0, 86400, 1200),
    ('30 m', 'cv_mid30', 30.0, 200.0, 40800, 700),
    ('40 m', 'cv_coarse40', 40.0, 280.0, 21600, 700),
    ('15 m', 'hi15', 15.0, 135.0, 96030, 1200),
]
print('%-13s %-8s %-10s %10s %12s %10s' % ('横向格距', '格数', '域(km)', '抵达口岸', '0-400s均速', '峰值速度'))
print('-' * 76)
res = []
for lab, d, dx, dy, nc, T in CASES:
    run = os.path.join(B, d)
    plt = os.path.join(run, 'output1_region1.plt')
    if not os.path.exists(plt):
        print('%-13s 无输出' % lab); continue
    ch = build_channel(run)
    meta = ch['meta']
    S = make_s_map(ch)
    d_port = np.hypot(ch['x'] - ch['px'] * meta['DX'], ch['y'] - (-ch['py'] * meta['DY']))
    S_PORT = ch['s'][int(np.argmin(d_port))] / 1000.0
    ts, front, vmax = [], [], []
    for t, a in iter_zones(plt):
        H = a[:, :, 4]
        wet = H > 0.05
        ts.append(t)
        front.append(float(S[wet].max()) if wet.any() else 0.0)
        vmax.append(float(np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2).max()))
    ts = np.array(ts); front = np.maximum.accumulate(np.array(front)); vmax = np.array(vmax)
    v = np.convolve(np.gradient(front * 1000.0, ts), np.ones(5) / 5, mode='same')
    kh = int(np.argmax(front >= S_PORT))
    hit = front[kh] >= S_PORT
    tat = ts[kh] if hit else None
    m = ts <= 400
    v400 = v[m].mean() if m.any() else float('nan')
    dom = '%.1f x %.1f' % (meta['NX'] * dx / 1000, meta['NY'] * dy / 1000)
    print('%-13s %-8d %-10s %10s %12.1f %10.1f'
          % (lab, nc, dom, ('%.0f s' % tat) if tat else '未到达', v400, v.max()))
    res.append(dict(label=lab, dx=dx, dy=dy, nc=nc, t_arrive=tat, v400=v400, vpeak=float(v.max()),
                    s_port=S_PORT, t=ts.tolist(), front=front.tolist()))
    json.dump({k: v for k, v in res[-1].items() if k not in ('t', 'front')},
              open(os.path.join(B, 'results', 'conv_%s.json' % d), 'w'), indent=2)

print()
print('观测: 400 s 抵达口岸')
print()
print('=== 收敛趋势（以 20 m 为基准）===')
base = next((r for r in res if r['label'].startswith('20 m')), None)
for r in sorted(res, key=lambda x: -x['dx']):
    if base and r['t_arrive'] and base['t_arrive']:
        print('  dx = %4.0f m  抵达 %6.0f s   与 20m 差 %+6.0f s (%.1f%%)'
              % (r['dx'], r['t_arrive'], r['t_arrive'] - base['t_arrive'],
                 100 * (r['t_arrive'] - base['t_arrive']) / base['t_arrive']))
    elif r['t_arrive']:
        print('  dx = %4.0f m  抵达 %6.0f s' % (r['dx'], r['t_arrive']))

# 绘图
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, axs = plt.subplots(1, 2, figsize=(14, 5.2))
ax = axs[0]
for r in res:
    ax.plot(r['t'], r['front'], lw=2.2, label='dx = %.0f m  (%s)' % (r['dx'], r['label']))
if base:
    ax.axhline(base['s_port'], color='c', ls='--', lw=1.8, label='Jilong port')
ax.axvline(400, color='r', ls=':', lw=2, label='observed 400 s')
ax.set_xlabel('time (s)'); ax.set_ylabel('front position (km)')
ax.set_title('Resolution convergence - front position')
ax.grid(alpha=0.3); ax.legend(fontsize=8.5)
ax = axs[1]
xs = [r['dx'] for r in res if r['t_arrive']]
ys = [r['t_arrive'] for r in res if r['t_arrive']]
o = np.argsort(xs)
ax.plot(np.array(xs)[o], np.array(ys)[o], 'o-', ms=9, lw=2.2, color='#1f77b4')
for x, y in zip(xs, ys):
    ax.annotate('%d m\n%.0f s' % (x, y), (x, y), textcoords='offset points',
                xytext=(0, 11), ha='center', fontsize=9)
ax.axhline(400, color='r', ls='--', lw=2, label='observed 400 s')
ax.set_xlabel('cross-channel grid spacing dx (m)')
ax.set_ylabel('model arrival time at port (s)')
ax.set_title('Grid convergence of arrival time')
ax.grid(alpha=0.3); ax.legend(fontsize=9)
fig.subplots_adjust(top=0.92, bottom=0.09, left=0.07, right=0.97, wspace=0.22)
p = os.path.join(B, 'results', 'figs', 'resolution_convergence.png')
fig.savefig(p, dpi=130); plt.close(fig)
print()
print('->', p)

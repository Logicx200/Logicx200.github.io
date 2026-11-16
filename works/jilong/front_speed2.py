# -*- coding: utf-8 -*-
"""
前缘速度分析（稳健版）
前缘定义：所有湿区像元 (H>0.05) 中，沿沟道中心线弧长 s 的最大值。
这样前缘位置单调不回退，速度由中心差分求得。
"""
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones

B = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(B, 'mf_fine')
OUT = os.path.join(B, 'results', 'figs')
os.makedirs(OUT, exist_ok=True)
meta = json.load(open(os.path.join(B, 'mf_real', 'meta.json')))
DX, DY, NX, NY = meta['DX'], meta['DY'], meta['NX'], meta['NY']
sc, sr = int(round(meta['src_col'])), int(round(meta['src_row']))
pc, pr = int(round(meta['port_col'])), int(round(meta['port_row']))
PORT_KM = (sc - pc) * DX / 1000.0
print('口岸距源区 直线 %.2f km' % PORT_KM)

# 为每个网格点计算它到中心线的最近弧长 s
sn = np.load(os.path.join(B, 'channel_sn.npz'))
si, xi, yi = sn['s'], sn['x'], sn['y']
cc_all, rr_all = np.meshgrid(np.arange(NX), np.arange(NY))
gx = cc_all * DX
gy = -rr_all * DY
# 最近中心线点（分块以省内存）
S_MAP = np.zeros((NY, NX), np.float32)
step = 120
for r0 in range(0, NY, step):
    r1 = min(NY, r0 + step)
    px = gx[r0:r1][:, None, :]
    py = gy[r0:r1][:, None, :]
    d2 = (px - xi[None, :, None]) ** 2 + (py - yi[None, :, None]) ** 2
    k = np.argmin(d2, axis=1)
    S_MAP[r0:r1] = si[k]
S_MAP = S_MAP / 1000.0
print('S_MAP 范围 %.2f .. %.2f km' % (S_MAP.min(), S_MAP.max()))

ts, front_s, vmax, hmax = [], [], [], []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    wet = H > 0.05
    s_front = float(S_MAP[wet].max()) if wet.any() else 0.0
    ts.append(t); front_s.append(s_front)
    vmax.append(float(np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2).max()))
    hmax.append(float(H.max()))

ts = np.array(ts); front_s = np.array(front_s)
vmax = np.array(vmax); hmax = np.array(hmax)
# 单调化（数值抖动）
front_mono = np.maximum.accumulate(front_s)
v = np.gradient(front_mono * 1000.0, ts)


def smooth(y, w=5):
    return np.convolve(y, np.ones(w) / w, mode='same')


v_s = smooth(v, 5)

# 口岸在中心线上的 s
d_port = np.hypot(xi - pc * DX, yi - (-pr * DY))
S_PORT = si[int(np.argmin(d_port))] / 1000.0
print('口岸在中心线上的 弧长 s = %.2f km' % S_PORT)
k_hit = np.argmax(front_mono >= S_PORT)
hit = front_mono[k_hit] >= S_PORT
print()
print('%8s %10s %12s %12s' % ('t(s)', '前缘s(km)', 'V前缘(m/s)', 'Vmax(m/s)'))
for i in range(0, len(ts), max(1, len(ts) // 18)):
    print('%8.0f %10.2f %12.1f %12.1f' % (ts[i], front_mono[i], v_s[i], vmax[i]))
print()
print('=== 关键结果 ===')
if hit:
    print('前缘抵达口岸(弧长 %.2f km): %.0f s' % (S_PORT, ts[k_hit]))
else:
    print('未在 %.0f s 内抵达口岸，末态前缘 %.2f / %.2f km' % (ts[-1], front_mono[-1], S_PORT))
print('峰值前缘速度 %.1f m/s @ t=%.0f s' % (v_s.max(), ts[int(np.argmax(v_s))]))
m = ts <= 400
print('0-400 s 前缘平均速度 %.1f m/s' % (v_s[m].mean()))
print('场内最大流速 %.1f m/s' % vmax.max())
print('观测: 400 s 推进约 22 km -> 平均 55 m/s')

np.savez(os.path.join(B, 'results', 'front_speed.npz'),
         t=ts, s=front_mono, v=v_s, vmax=vmax, hmax=hmax)

# ============ 绘图 ============
fig, axs = plt.subplots(2, 1, figsize=(11.5, 9.2), sharex=True)
ax = axs[0]
ax.plot(ts, front_mono, 'o-', ms=3.8, lw=2.0, color='#1f77b4', label='front position (arc length s)')
ax.axhline(S_PORT, color='c', ls='--', lw=2, label='Jilong port  (s = %.1f km)' % S_PORT)
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
if hit:
    ax.plot(ts[k_hit], front_mono[k_hit], 'r*', ms=20, mec='k', zorder=6)
    ax.annotate('model arrival  %.0f s' % ts[k_hit], (ts[k_hit], front_mono[k_hit]),
                textcoords='offset points', xytext=(14, -22), fontsize=11, color='r')
ax.set_ylabel('front position along channel (km)')
ax.set_title('Front position vs time   (Jilong ice avalanche, mu=0.005)')
ax.grid(alpha=0.3); ax.legend(fontsize=9, loc='upper left')

ax = axs[1]
ax.plot(ts, v_s, '-', lw=2.8, color='#d62728', label='front propagation speed')
ax.plot(ts, vmax, '-', lw=1.3, color='gray', alpha=0.6, label='max field velocity (U,V)')
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
ax.axhline(55.0, color='g', ls='-.', lw=2.2, label='observed mean 22 km / 400 s = 55 m/s')
if hit:
    ax.axvline(ts[k_hit], color='r', ls='--', lw=1.6, alpha=0.7)
ax.set_xlabel('time (s)'); ax.set_ylabel('speed (m/s)')
ax.set_title('Front propagation speed vs time')
ax.grid(alpha=0.3); ax.legend(fontsize=9)
fig.subplots_adjust(top=0.94, bottom=0.06, left=0.085, right=0.97, hspace=0.2)
p = os.path.join(OUT, 'front_speed.png')
fig.savefig(p, dpi=130)
plt.close(fig)
print('->', p)

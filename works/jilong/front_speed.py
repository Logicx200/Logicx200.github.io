# -*- coding: utf-8 -*-
"""
前缘运动速度分析：
 - 前缘位置 vs 时间（沿程弧长 + 直线距离两种度量）
 - 前缘速度 vs 时间（对位置序列求导，含平滑）
 - 与观测对比（观测: 400 s 内推进约 22 km, 平均约 55 m/s）
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
DX, DY = meta['DX'], meta['DY']
sc = int(round(meta['src_col']))
pc = int(round(meta['port_col']))
pr = int(round(meta['port_row']))
PORT_X = (sc - pc) * DX / 1000.0     # 口岸距源区的直线距离 (km)

# 沿沟道中心线的弧长坐标
sn = np.load(os.path.join(B, 'channel_sn.npz'))
si = sn['s']
col_of_s = np.clip(np.round(sn['x'] / DX).astype(int), 0, meta['NX'] - 1)
# 建立 “前缘列 -> 沿程弧长” 的映射
col_to_s = {}
for k in range(len(si)):
    c = int(col_of_s[k])
    col_to_s[c] = max(col_to_s.get(c, 0.0), si[k])

ts, front_col, front_s, vmax = [], [], [], []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    spd = np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2)
    wet = H > 0.05
    cc = np.where(wet.any(axis=0))[0]
    fc = int(cc.min()) if cc.size else 10 ** 6
    ts.append(t); front_col.append(fc)
    front_s.append(col_to_s.get(fc, (sc - fc) * DX))
    vmax.append(float(spd.max()))

ts = np.array(ts)
front_s = np.array(front_s) / 1000.0          # km
front_col = np.array(front_col)
direct = (sc - front_col) * DX / 1000.0       # km 直线推进
vmax = np.array(vmax)

# 前缘速度: 中心差分 + 轻度平滑
dt = np.gradient(ts)
v_s = np.gradient(front_s * 1000.0, ts)       # m/s 沿程
v_d = np.gradient(direct * 1000.0, ts)        # m/s 直线
# 5 点滑动平均
def smooth(y, w=5):
    k = np.ones(w) / w
    return np.convolve(y, k, mode='same')
v_s_s = smooth(v_s, 5)
v_d_s = smooth(v_d, 5)

np.savez(os.path.join(B, 'results', 'front_speed.npz'),
         t=ts, s=front_s, direct=direct, v_s=v_s, v_d=v_d,
         v_s_smooth=v_s_s, v_d_smooth=v_d_s, vmax=vmax)

print('%8s %10s %10s %10s %12s' % ('t(s)', '沿程km', '直线km', 'V沿程m/s', 'Vmax场内'))
for i in range(0, len(ts), max(1, len(ts) // 20)):
    print('%8.0f %10.2f %10.2f %10.1f %12.1f'
          % (ts[i], front_s[i], direct[i], v_s_s[i], vmax[i]))
    if direct[i] >= PORT_X:
        print('   ^ 首次抵达口岸 (直线 %.2f km)' % PORT_X)
        break

# ============ 绘图 ============
fig, axs = plt.subplots(2, 1, figsize=(11, 8.6), sharex=True)
ax = axs[0]
ax.plot(ts, front_s, 'o-', ms=3.5, lw=1.8, color='#1f77b4', label='along-channel arc length')
ax.plot(ts, direct, 's-', ms=3.5, lw=1.8, color='#ff7f0e', label='straight-line from source')
ax.axhline(PORT_X, color='c', ls='--', lw=2, label='Jilong port (straight %.2f km)' % PORT_X)
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
k_hit = np.argmax(direct >= PORT_X)
if direct[k_hit] >= PORT_X:
    ax.plot(ts[k_hit], direct[k_hit], 'r*', ms=18, mec='k', zorder=5)
    ax.annotate('model arrival %.0f s' % ts[k_hit], (ts[k_hit], direct[k_hit]),
                textcoords='offset points', xytext=(12, -18), fontsize=10, color='r')
ax.set_ylabel('front position (km)')
ax.set_title('Front position vs time')
ax.grid(alpha=0.3); ax.legend(fontsize=9, loc='upper left')

ax = axs[1]
ax.plot(ts, v_s_s, lw=2.4, color='#1f77b4', label='front speed (along-channel)')
ax.plot(ts, v_d_s, lw=2.0, color='#ff7f0e', alpha=0.85, label='front speed (straight-line)')
ax.plot(ts, vmax, lw=1.2, color='gray', alpha=0.55, label='max velocity in field (U,V)')
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
obs_v = 22000.0 / 400.0
ax.axhline(obs_v, color='g', ls='-.', lw=2, label='observed mean ≈ %.0f m/s' % obs_v)
ax.set_xlabel('time (s)'); ax.set_ylabel('speed (m/s)')
ax.set_title('Front propagation speed vs time')
ax.grid(alpha=0.3); ax.legend(fontsize=9)
fig.subplots_adjust(top=0.94, bottom=0.07, left=0.08, right=0.97, hspace=0.22)
p = os.path.join(OUT, 'front_speed.png')
fig.savefig(p, dpi=130)
plt.close(fig)
print('->', p)

print()
print('=== 速度统计 ===')
m = ts <= 400
print('0-400 s 前缘平均速度（沿程）: %.1f m/s' % v_s_s[m].mean())
print('0-400 s 前缘平均速度（直线）: %.1f m/s' % v_d_s[m].mean())
print('峰值前缘速度（沿程）: %.1f m/s @ t=%.0f s' % (v_s_s.max(), ts[np.argmax(v_s_s)]))
print('观测 22 km / 400 s = %.1f m/s' % obs_v)
print('模型抵达口岸时间: %s' % ('%.0f s' % ts[k_hit] if direct[k_hit] >= PORT_X else '未到达'))

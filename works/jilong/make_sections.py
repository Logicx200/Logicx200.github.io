# -*- coding: utf-8 -*-
"""
按时间分阶段切面图：
 (1) 纵剖面：沿沟道 s 的流动厚度 H(s) 随时间演化（多时刻叠图 + 瀑布图）
 (2) 时间-距离图（Hovmoller）：x=s, y=t, 色=H
 (3) 横断面：在源区/堰塞湖/口岸三个位置的横向断面
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
NX, NY = meta['NX'], meta['NY']
DX, DY = meta['DX'], meta['DY']
E0, N0, N1 = meta['E0'], meta['N0'], meta['N1']
sn = np.load(os.path.join(B, 'channel_sn.npz'))
si, xi, yi = sn['s'], sn['x'], sn['y']
s_km = si / 1000.0
print('中心线 %d 点, 总长 %.2f km' % (len(si), s_km[-1]))

# 采样点 -> 网格 (col,row)
col = np.clip(np.round((xi + E0 * 0 + (E0 - E0)) / DX + (np.array(0))).astype(int), 0, NX - 1)
# 注意: xi 存的是 col*DX, 所以 col = xi/DX
col = np.clip(np.round(xi / DX).astype(int), 0, NX - 1)
row = np.clip(np.round(-yi / DY).astype(int), 0, NY - 1)
print('col %d..%d   row %d..%d' % (col.min(), col.max(), row.min(), row.max()))

# 读取所有帧，只沿中心线取值
times, prof = [], []
tsn = []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    hs = H[row, col]
    tsn.append(t)
    prof.append(hs)
    # 时间-距离图用更密的采样
prof = np.array(prof)
tsn = np.array(tsn)
print('帧数 %d, t=%.0f..%.0f s' % (len(tsn), tsn[0], tsn[-1]))
np.savez(os.path.join(B, 'results', 'profile_sn.npz'), t=tsn, s=s_km, H=prof)

# ============ (1) 纵剖面多时刻叠图 ============
sel = [0, 20, 40, 60, 80, 100, 120, 160, 200, 260, 320, 400, 480, 600, 720]
sel = [i for i in sel if i < len(tsn)]
fig, ax = plt.subplots(figsize=(13, 6.2))
cmap = plt.cm.viridis(np.linspace(0, 0.95, len(sel)))
for k, i in enumerate(sel):
    ax.plot(s_km, prof[i], lw=1.9, color=cmap[k], label='t = %.0f s' % tsn[i])
ax.axvline(9.37, color='magenta', ls='--', lw=2, alpha=0.8)
ax.text(9.5, ax.get_ylim()[1] * 0.93, 'barrier lake', color='magenta', fontsize=10)
ax.axvline(28.11, color='c', ls='--', lw=2, alpha=0.9)
ax.text(26.2, ax.get_ylim()[1] * 0.93, 'Jilong port', color='c', fontsize=10)
ax.set_xlabel('distance along channel from source  s (km)')
ax.set_ylabel('flow depth  H (m)')
ax.set_title('Longitudinal profiles along the channel, staged by time')
ax.grid(alpha=0.3); ax.legend(fontsize=8, ncol=3)
p1 = os.path.join(OUT, 'section_longitudinal.png')
fig.savefig(p1, dpi=130, bbox_inches='tight'); plt.close(fig)
print('->', p1)

# ============ (2) 时间-距离图 ============
fig, ax = plt.subplots(figsize=(11, 6.4))
m = ax.pcolormesh(s_km, tsn, prof, cmap='turbo', vmin=0, vmax=120, shading='auto')
ax.axhline(400, color='w', ls=':', lw=2)
ax.text(0.4, 415, 'observed arrival at port (400 s)', color='w', fontsize=9)
ax.axvline(9.37, color='magenta', ls='--', lw=1.6)
ax.axvline(28.11, color='c', ls='--', lw=1.6)
ax.text(9.5, tsn[-1] * 0.97, 'lake', color='magenta', fontsize=9)
ax.text(26.4, tsn[-1] * 0.97, 'port', color='c', fontsize=9)
ax.set_xlabel('distance along channel  s (km)')
ax.set_ylabel('time (s)')
ax.set_title('Time-distance diagram (Hovmoller) of flow depth')
fig.colorbar(m, ax=ax, label='flow depth H (m)')
p2 = os.path.join(OUT, 'section_hovmoller.png')
fig.savefig(p2, dpi=130, bbox_inches='tight'); plt.close(fig)
print('->', p2)

# ============ (3) 横断面 ============
# 在若干 s 处取垂直于中心线的断面
def cross_section(a, s_target, half=1500.0, step=30.0):
    k = int(np.argmin(np.abs(si - s_target)))
    k2 = min(k + 3, len(si) - 1)
    dx_ = xi[k2] - xi[k]; dy_ = yi[k2] - yi[k]
    nrm = np.hypot(dx_, dy_)
    if nrm == 0:
        return None, None
    tx, ty = dx_ / nrm, dy_ / nrm
    nx_, ny_ = -ty, tx
    ns = np.arange(-half, half + 1, step)
    px = xi[k] + nx_ * ns
    py = yi[k] + ny_ * ns
    cc = np.clip(np.round(px / DX).astype(int), 0, NX - 1)
    rr = np.clip(np.round(-py / DY).astype(int), 0, NY - 1)
    return ns / 1000.0, a[rr, cc, 4]


Z = np.load(os.path.join(B, 'mf_real', 'Z.npy'))
frames = {}
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    frames[round(t)] = a
want = [40, 100, 200, 300, 400, 540, 720]
want = [w for w in want if w in frames] or [min(frames)]
stations = [('source reach', 2.0), ('barrier lake', 9.37), ('mid valley', 18.0), ('Jilong port', 28.11)]
fig, axs = plt.subplots(len(stations), 1, figsize=(11, 3.0 * len(stations)), squeeze=False)
for si_, (nm, st) in enumerate(stations):
    axx = axs[si_][0]
    cmap2 = plt.cm.plasma(np.linspace(0, 0.9, len(want)))
    for k, w in enumerate(want):
        ns, hv = cross_section(frames[w], st)
        if ns is None:
            continue
        axx.plot(ns, hv, lw=1.9, color=cmap2[k], label='t = %d s' % w)
    # 地形断面
    ns, _ = cross_section(frames[want[0]], st)
    k = int(np.argmin(np.abs(si - st)))
    dx_ = xi[min(k + 3, len(si) - 1)] - xi[k]; dy_ = yi[min(k + 3, len(si) - 1)] - yi[k]
    nrm = np.hypot(dx_, dy_)
    tx, ty = dx_ / nrm, dy_ / nrm
    nxv, nyv = -ty, tx
    nsx = np.arange(-1500, 1501, 30)
    px = xi[k] + nxv * nsx; py = yi[k] + nyv * nsx
    cc = np.clip(np.round(px / DX).astype(int), 0, NX - 1)
    rr = np.clip(np.round(-py / DY).astype(int), 0, NY - 1)
    axx.plot(nsx / 1000.0, Z[rr, cc], 'k--', lw=1.4, label='bed elevation')
    axx.set_title('%s   (s = %.2f km)' % (nm, st), fontsize=10)
    axx.set_xlabel('cross-channel offset (km)')
    axx.set_ylabel('H (m) / bed (m)')
    axx.grid(alpha=0.3); axx.legend(fontsize=7, ncol=3)
fig.suptitle('Cross-channel sections at four stations', fontsize=13)
fig.tight_layout()
p3 = os.path.join(OUT, 'section_cross.png')
fig.savefig(p3, dpi=120, bbox_inches='tight'); plt.close(fig)
print('->', p3)

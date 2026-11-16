# -*- coding: utf-8 -*-
"""
高精度算例(mf_hi, 20m x 140m, 121帧)全套成果：
 1) 分阶段网格图
 2) 全帧接触表
 3) 高帧率动画
 4) 前缘位置与速度-时间图（弧长定义）
"""
import os
import sys
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import matplotlib.animation as anim
sys.path.insert(0, r'F:\DeepSeek工作区\jilong')
from plt_reader import iter_zones
from chanlib import build_channel, make_s_map

B = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(B, 'mf_hi')
FIG = os.path.join(B, 'results', 'figs')
os.makedirs(FIG, exist_ok=True)

print('=== 构建沟道曲线坐标 ===')
ch = build_channel(RUN)
meta = ch['meta']
NX, NY, DX, DY = meta['NX'], meta['NY'], meta['DX'], meta['DY']
Z = np.load(os.path.join(RUN, 'Z.npy'))
Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                     (meta['N1'] - np.arange(NY) * DY) / 1000.0)
SRC = (Xg[int(round(meta['src_row'])), int(round(meta['src_col']))],
       Yg[int(round(meta['src_row'])), int(round(meta['src_col']))])
LAKE = (Xg[int(round(meta['lake_row'])), int(round(meta['lake_col']))],
        Yg[int(round(meta['lake_row'])), int(round(meta['lake_col']))])
PORT = (Xg[int(round(meta['port_row'])), int(round(meta['port_col']))],
        Yg[int(round(meta['port_row'])), int(round(meta['port_col']))])
EXT = [Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]]
print('中心线总长 %.2f km' % (ch['s'][-1] / 1000))

print('=== 读取帧 ===')
frames = [(t, a[:, :, 4]) for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt'))]
print('%d 帧 t=%.0f..%.0f' % (len(frames), frames[0][0], frames[-1][0]))

ls = LightSource(azdeg=315, altdeg=45)
rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)


def draw(ax, idx, title, vmax=120, small=False):
    t, H = frames[idx]
    ax.imshow(rgb, extent=EXT, origin='upper', alpha=0.92)
    m = ax.pcolormesh(Xg, Yg, np.where(H > 0.05, H, np.nan), cmap='turbo',
                      vmin=0, vmax=vmax, shading='auto', alpha=0.93)
    ax.plot(PORT[0], PORT[1], 'c*', ms=10 if small else 16, mec='k')
    ax.plot(SRC[0], SRC[1], 'wo', ms=5 if small else 9, mec='k')
    ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=5 if small else 9, mec='k')
    ax.set_title(title, fontsize=7.6 if small else 10, pad=3)
    ax.set_aspect('equal')
    ax.tick_params(labelsize=5.5 if small else 7.5)
    return m


def pick(tt):
    return min(range(len(frames)), key=lambda i: abs(frames[i][0] - tt))


# ---------- 1) 阶段网格 4x4 ----------
STAGES = [0, 20, 50, 80, 100, 150, 200, 250, 300, 350, 400, 450, 500, 540, 700, 1000]
cols, rows = 4, 4
fig, axes = plt.subplots(rows, cols, figsize=(4.6 * cols, 3.3 * rows + 1.2))
m = None
for k, st in enumerate(STAGES):
    ax = axes[k // cols][k % cols]
    idx = pick(st)
    t, H = frames[idx]
    note = ''
    if st == 80:
        note = '  <- barrier lake'
    if st in (500, 540):
        note = '  <- Jilong port'
    m = draw(ax, idx, 't = %.0f s    H$_{max}$ = %.0f m%s' % (t, H.max(), note))
for k in range(len(STAGES), rows * cols):
    axes[k // cols][k % cols].axis('off')
fig.subplots_adjust(top=0.93, bottom=0.055, left=0.028, right=0.905, hspace=0.30, wspace=0.14)
cax = fig.add_axes([0.918, 0.18, 0.014, 0.62])
fig.colorbar(m, cax=cax, label='flow depth H (m)')
fig.suptitle('Jilong ice avalanche - HIGH-RESOLUTION simulation stages  (20 m x 140 m grid, 86,400 cells)\n'
             'white dot: source    magenta square: barrier lake    cyan star: Jilong port',
             fontsize=12.5, y=0.982)
p1 = os.path.join(FIG, 'hi_stages_grid.png')
fig.savefig(p1, dpi=115); plt.close(fig)
print('->', p1)

# ---------- 2) 全帧接触表 11x11 ----------
n = len(frames); cc = 11; rr = int(np.ceil(n / cc))
fig, axes = plt.subplots(rr, cc, figsize=(1.75 * cc, 1.5 * rr + 1.0))
for k in range(rr * cc):
    ax = axes[k // cc][k % cc]
    if k >= n:
        ax.axis('off'); continue
    t, H = frames[k]
    m = draw(ax, k, '%.0f' % t, small=True)
    ax.set_xticks([]); ax.set_yticks([])
fig.subplots_adjust(top=0.945, bottom=0.015, left=0.008, right=0.905, hspace=0.16, wspace=0.04)
cax = fig.add_axes([0.917, 0.14, 0.011, 0.72])
fig.colorbar(m, cax=cax, label='H (m)')
fig.suptitle('All %d frames (10 s interval, 0-1200 s) - high-resolution run' % n, fontsize=12.5, y=0.985)
p2 = os.path.join(FIG, 'hi_contact_sheet.png')
fig.savefig(p2, dpi=125); plt.close(fig)
print('->', p2)

# ---------- 3) 动画 ----------
FPS = 15
fig, ax = plt.subplots(figsize=(11.5, 6.8))
fig.subplots_adjust(top=0.88, bottom=0.09, left=0.07, right=0.90)
ax.imshow(rgb, extent=EXT, origin='upper', alpha=0.92)
mesh = ax.pcolormesh(Xg, Yg, np.zeros_like(Z), cmap='turbo', vmin=0, vmax=120,
                     shading='auto', alpha=0.9)
ax.plot(PORT[0], PORT[1], 'c*', ms=20, mec='k', label='Jilong port (arrival 510-540 s)')
ax.plot(SRC[0], SRC[1], 'wo', ms=10, mec='k', label='ice-avalanche source')
ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=10, mec='k', label='barrier lake (hit at 80 s)')
ax.set_aspect('equal'); ax.set_xlabel('E (km)'); ax.set_ylabel('N (km)')
ax.legend(loc='lower left', fontsize=9, framealpha=0.9)
cax = fig.add_axes([0.915, 0.16, 0.016, 0.66])
fig.colorbar(mesh, cax=cax, label='flow depth H (m)')
tt = fig.suptitle('', fontsize=13, y=0.965)


def upd(i):
    t, H = frames[i]
    mesh.set_array(H.ravel())
    tt.set_text('Jilong ice avalanche - high-res      t = %.0f s      H$_{max}$ = %.0f m'
                % (t, H.max()))
    return mesh, tt


an = anim.FuncAnimation(fig, upd, frames=len(frames), interval=1000 / FPS, blit=False)
p3 = os.path.join(B, 'results', 'hi_animation_15fps.gif')
an.save(p3, writer=anim.PillowWriter(fps=FPS))
plt.close(fig)
print('-> %s (%.2f MB, %d 帧)' % (p3, os.path.getsize(p3) / 1e6, len(frames)))

# ---------- 4) 前缘位置与速度 ----------
S = make_s_map(ch)
print('S_MAP %.2f .. %.2f km' % (S.min(), S.max()))
d_port = np.hypot(ch['x'] - ch['px'] * DX, ch['y'] - (-ch['py'] * DY))
S_PORT = ch['s'][int(np.argmin(d_port))] / 1000.0
ts, front, vmax = [], [], []
for t, a in iter_zones(os.path.join(RUN, 'output1_region1.plt')):
    H = a[:, :, 4]
    wet = H > 0.05
    ts.append(t)
    front.append(float(S[wet].max()) if wet.any() else 0.0)
    vmax.append(float(np.sqrt(a[:, :, 5] ** 2 + a[:, :, 6] ** 2).max()))
ts = np.array(ts); front = np.maximum.accumulate(np.array(front)); vmax = np.array(vmax)
v = np.convolve(np.gradient(front * 1000.0, ts), np.ones(5) / 5, mode='same')
kh = int(np.argmax(front >= S_PORT))
hit = front[kh] >= S_PORT
np.savez(os.path.join(B, 'results', 'hi_front_speed.npz'), t=ts, s=front, v=v, vmax=vmax)

fig, axs = plt.subplots(2, 1, figsize=(11.5, 9.2), sharex=True)
ax = axs[0]
ax.plot(ts, front, lw=2.4, color='#1f77b4', label='front position (arc length)')
ax.axhline(S_PORT, color='c', ls='--', lw=2, label='Jilong port (s = %.1f km)' % S_PORT)
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
if hit:
    ax.plot(ts[kh], front[kh], 'r*', ms=20, mec='k', zorder=6)
    ax.annotate('model arrival %.0f s' % ts[kh], (ts[kh], front[kh]),
                textcoords='offset points', xytext=(14, -22), fontsize=11, color='r')
ax.set_ylabel('front position (km)'); ax.grid(alpha=0.3); ax.legend(fontsize=9)
ax.set_title('Front position vs time - high-resolution run (20 m x 140 m)')
ax = axs[1]
ax.plot(ts, v, lw=2.8, color='#d62728', label='front propagation speed')
ax.plot(ts, vmax, lw=1.2, color='gray', alpha=0.55, label='max field velocity')
ax.axvline(400, color='r', ls=':', lw=2, label='observed arrival (400 s)')
ax.axhline(55.0, color='g', ls='-.', lw=2.2, label='observed mean 22 km / 400 s = 55 m/s')
ax.set_xlabel('time (s)'); ax.set_ylabel('speed (m/s)')
ax.grid(alpha=0.3); ax.legend(fontsize=9)
ax.set_title('Front propagation speed vs time')
fig.subplots_adjust(top=0.94, bottom=0.06, left=0.085, right=0.97, hspace=0.2)
p4 = os.path.join(FIG, 'hi_front_speed.png')
fig.savefig(p4, dpi=130); plt.close(fig)
print('->', p4)
print()
print('前缘抵达口岸: %s' % ('%.0f s' % ts[kh] if hit else '未到达'))
print('峰值前缘速度 %.1f m/s' % v.max())
print('0-400s 平均 %.1f m/s (观测 55)' % v[ts <= 400].mean())

# -*- coding: utf-8 -*-
"""
通用出图：为任意算例生成
 1) 分阶段网格图 (4x4)
 2) 高潮期细节图 (4x3, 0-400s)
 3) 高帧率动画
 4) 全帧接触表（帧数 <= 130 时）
用法: python make_run_outputs.py <run_dir> <tag> [fps]
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

B = r'F:\DeepSeek工作区\jilong'
FIG = os.path.join(B, 'results', 'figs')
os.makedirs(FIG, exist_ok=True)


def run(run_dir, tag, fps=15):
    meta = json.load(open(os.path.join(run_dir, 'meta.json')))
    Z = np.load(os.path.join(run_dir, 'Z.npy'))
    NX, NY, DX, DY = meta['NX'], meta['NY'], meta['DX'], meta['DY']
    Xg, Yg = np.meshgrid((meta['E0'] + np.arange(NX) * DX) / 1000.0,
                         (meta['N1'] - np.arange(NY) * DY) / 1000.0)
    SRC = (Xg[int(round(meta['src_row'])), int(round(meta['src_col']))],
           Yg[int(round(meta['src_row'])), int(round(meta['src_col']))])
    LAKE = (Xg[int(round(meta['lake_row'])), int(round(meta['lake_col']))],
            Yg[int(round(meta['lake_row'])), int(round(meta['lake_col']))])
    PORT = (Xg[int(round(meta['port_row'])), int(round(meta['port_col']))],
            Yg[int(round(meta['port_row'])), int(round(meta['port_col']))])
    EXT = [Xg[0, 0], Xg[0, -1], Yg[-1, 0], Yg[0, 0]]
    gridtxt = '%d x %d = %s cells   (dx = %.0f m, dy = %.0f m)' % (
        NX, NY, format(NX * NY, ','), DX, DY)

    print('读取 %s ...' % tag)
    frames = [(t, a[:, :, 4]) for t, a in iter_zones(os.path.join(run_dir, 'output1_region1.plt'))]
    print('  %d 帧  t=%.0f..%.0f s' % (len(frames), frames[0][0], frames[-1][0]))

    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(Z, cmap=plt.cm.Greys, blend_mode='soft', vert_exag=2, dx=DX, dy=DY)

    def pick(tt):
        return min(range(len(frames)), key=lambda i: abs(frames[i][0] - tt))

    def draw(ax, idx, title, vmax=120, small=False, cmap='turbo'):
        t, H = frames[idx]
        ax.imshow(rgb, extent=EXT, origin='upper', alpha=0.92)
        m = ax.pcolormesh(Xg, Yg, np.where(H > 0.05, H, np.nan), cmap=cmap,
                          vmin=0, vmax=vmax, shading='auto', alpha=0.93)
        ax.plot(PORT[0], PORT[1], 'c*', ms=9 if small else 16, mec='k')
        ax.plot(SRC[0], SRC[1], 'wo', ms=5 if small else 9, mec='k')
        ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=5 if small else 9, mec='k')
        ax.set_title(title, fontsize=7.4 if small else 10, pad=3)
        ax.set_aspect('equal')
        ax.tick_params(labelsize=5.4 if small else 7.5)
        return m

    # ---------- 1) 阶段网格 4x4 ----------
    STAGES = [0, 20, 50, 80, 100, 150, 200, 250, 300, 350, 400, 450, 500, 540, 700, 1000]
    STAGES = [s for s in STAGES if s <= frames[-1][0]]
    cols = 4
    rows = int(np.ceil(len(STAGES) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.6 * cols, 3.3 * rows + 1.2))
    axes = np.atleast_2d(axes)
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
    fig.suptitle('Jilong ice avalanche - simulation stages   [%s]\n%s\n'
                 'white dot: source    magenta square: barrier lake    cyan star: Jilong port'
                 % (tag, gridtxt), fontsize=12.5, y=0.982)
    p1 = os.path.join(FIG, '%s_stages_grid.png' % tag)
    fig.savefig(p1, dpi=115); plt.close(fig)
    print('->', p1)

    # ---------- 2) 高潮期 0-400 s 细节 ----------
    CORE = [0, 20, 40, 60, 80, 100, 140, 180, 220, 260, 320, 400]
    CORE = [s for s in CORE if s <= frames[-1][0]]
    cols = 4
    rows = int(np.ceil(len(CORE) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.6 * cols, 3.3 * rows + 1.2))
    axes = np.atleast_2d(axes)
    m = None
    for k, st in enumerate(CORE):
        ax = axes[k // cols][k % cols]
        idx = pick(st)
        t, H = frames[idx]
        m = draw(ax, idx, 't = %.0f s    H$_{max}$ = %.0f m' % (t, H.max()))
    for k in range(len(CORE), rows * cols):
        axes[k // cols][k % cols].axis('off')
    fig.subplots_adjust(top=0.91, bottom=0.055, left=0.028, right=0.905, hspace=0.30, wspace=0.14)
    cax = fig.add_axes([0.918, 0.18, 0.014, 0.62])
    fig.colorbar(m, cax=cax, label='flow depth H (m)')
    fig.suptitle('Jilong ice avalanche - main dynamic phase (0-400 s)   [%s]\n%s'
                 % (tag, gridtxt), fontsize=12.5, y=0.975)
    p2 = os.path.join(FIG, '%s_core_grid.png' % tag)
    fig.savefig(p2, dpi=115); plt.close(fig)
    print('->', p2)

    # ---------- 3) 动画 ----------
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    fig.subplots_adjust(top=0.88, bottom=0.09, left=0.07, right=0.90)
    ax.imshow(rgb, extent=EXT, origin='upper', alpha=0.92)
    mesh = ax.pcolormesh(Xg, Yg, np.zeros_like(Z), cmap='turbo', vmin=0, vmax=120,
                         shading='auto', alpha=0.9)
    ax.plot(PORT[0], PORT[1], 'c*', ms=20, mec='k', label='Jilong port (impact ~440 s)')
    ax.plot(SRC[0], SRC[1], 'wo', ms=10, mec='k', label='ice-avalanche source')
    ax.plot(LAKE[0], LAKE[1], 's', color='magenta', ms=10, mec='k', label='barrier lake (hit ~80 s)')
    ax.set_aspect('equal'); ax.set_xlabel('E (km)'); ax.set_ylabel('N (km)')
    ax.legend(loc='lower left', fontsize=9, framealpha=0.9)
    cax = fig.add_axes([0.915, 0.16, 0.016, 0.66])
    fig.colorbar(mesh, cax=cax, label='flow depth H (m)')
    tt = fig.suptitle('', fontsize=12.5, y=0.965)

    def upd(i):
        t, H = frames[i]
        mesh.set_array(H.ravel())
        tt.set_text('Jilong ice avalanche  [%s]      t = %.0f s      H$_{max}$ = %.0f m'
                    % (tag, t, H.max()))
        return mesh, tt

    an = anim.FuncAnimation(fig, upd, frames=len(frames), interval=1000 / fps, blit=False)
    p3 = os.path.join(B, 'results', '%s_animation_%dfps.gif' % (tag, fps))
    an.save(p3, writer=anim.PillowWriter(fps=fps))
    plt.close(fig)
    print('-> %s (%.2f MB)' % (p3, os.path.getsize(p3) / 1e6))

    # ---------- 4) 接触表 ----------
    n = len(frames)
    if n <= 130:
        cc = 11
        rr = int(np.ceil(n / cc))
        fig, axes = plt.subplots(rr, cc, figsize=(1.75 * cc, 1.5 * rr + 1.0))
        for k in range(rr * cc):
            ax = axes[k // cc][k % cc]
            if k >= n:
                ax.axis('off'); continue
            t, H = frames[k]
            m = draw(ax, k, '%.0f' % t, small=True)
            ax.set_xticks([]); ax.set_yticks([])
        fig.subplots_adjust(top=0.945, bottom=0.015, left=0.008, right=0.905,
                            hspace=0.16, wspace=0.04)
        cax = fig.add_axes([0.917, 0.14, 0.011, 0.72])
        fig.colorbar(m, cax=cax, label='H (m)')
        fig.suptitle('All %d frames (%.0f s interval) - %s' % (
            n, frames[1][0] - frames[0][0] if n > 1 else 0, gridtxt), fontsize=12, y=0.985)
        p4 = os.path.join(FIG, '%s_contact_sheet.png' % tag)
        fig.savefig(p4, dpi=125); plt.close(fig)
        print('->', p4)


if __name__ == '__main__':
    d = sys.argv[1] if len(sys.argv) > 1 else 'hi15'
    tag = sys.argv[2] if len(sys.argv) > 2 else d
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    run(os.path.join(B, d), tag, fps)

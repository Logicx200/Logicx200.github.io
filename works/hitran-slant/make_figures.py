# -*- coding: utf-8 -*-
"""Build the slant-path transmittance figures from the computed spectra."""
import os, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
from matplotlib.gridspec import GridSpec
from scipy.ndimage import uniform_filter1d

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, 'figures')
os.makedirs(OUTDIR, exist_ok=True)

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
    'axes.unicode_minus': False,
    'font.size': 10,
    'axes.linewidth': 0.9,
    'savefig.dpi': 300,
})

C_TOT = '#111111'
C_H2O = '#1f6fd0'
C_CO2 = '#d62728'
C_CH4 = '#2ca02c'
LBL = {'tr_H2O': 'H$_2$O', 'tr_CO2': 'CO$_2$', 'tr_CH4': 'CH$_4$'}
WLTICKS = [2, 2.5, 3, 4, 5, 6, 8, 10, 12, 14, 16, 20]


def top_wl_axis(ax):
    ax2 = ax.secondary_xaxis('top', functions=(lambda nu: 1e4 / np.maximum(nu, 1e-6),
                                               lambda wl: 1e4 / np.maximum(wl, 1e-9)))
    ax2.set_xlabel('波长 (μm)', labelpad=2)
    return ax2


def smooth_ds(x, y, width=20.0):
    """Boxcar smooth over `width` cm^-1 then decimate for plotting."""
    step = x[1] - x[0]
    n = max(1, int(round(width / step)))
    ys = uniform_filter1d(y, n, mode='nearest')
    k = max(1, int(round(0.02 / step)))
    return x[::k], ys[::k]


def main():
    d = np.load(os.path.join(BASE, 'slant_spectrum.npz'))
    z8 = np.load(os.path.join(BASE, 'slant_zoom_8_14.npz'))
    z35 = np.load(os.path.join(BASE, 'slant_zoom_3_5.npz'))

    fig = plt.figure(figsize=(12.8, 11.4))
    gs = GridSpec(3, 1, height_ratios=[1.35, 1.0, 1.0], hspace=0.52,
                  left=0.075, right=0.975, top=0.925, bottom=0.055)

    fig.suptitle('HITRAN2020 逐线计算：8 km 平台至 20 km 地面斜程（21.54 km）大气红外透过率',
                 fontsize=12.5, y=0.985)

    # ---------------- panel (a): 2-20 um overview ----------------
    ax = fig.add_subplot(gs[0])
    x = d['grid']
    xs, ys = smooth_ds(x, d['tr_total'])
    ax.plot(xs, ys, color=C_TOT, lw=1.4, label='总透过率', zorder=5)
    for key, c in (('tr_H2O', C_H2O), ('tr_CO2', C_CO2), ('tr_CH4', C_CH4)):
        xs, ys = smooth_ds(x, d[key])
        ax.plot(xs, ys, color=c, lw=0.9, alpha=0.9, label=LBL[key])
    ax.set_xlim(500, 5000)
    ax.set_ylim(0, 1.06)
    ax.set_ylabel('斜程透过率  $T$')
    ax.set_xlabel('波数 (cm$^{-1}$)')
    ax2 = top_wl_axis(ax)
    ax2.set_xticks(WLTICKS)
    ax2.set_xticklabels(['%g' % w for w in WLTICKS])
    ax.grid(alpha=0.25, lw=0.5)
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax.text(0.008, 0.955, '(a) 全红外波段（20 cm$^{-1}$ 平滑显示）', transform=ax.transAxes,
            fontsize=10.5, fontweight='bold', va='top',
            bbox=dict(facecolor='white', alpha=0.72, edgecolor='none', pad=1.6))
    ax.legend(loc='upper right', bbox_to_anchor=(0.995, 0.99), ncol=4,
              fontsize=9, framealpha=0.92)

    bands = [(667, 'CO$_2$ 15 μm'), (1300, 'CH$_4$ 7.7 μm'), (1590, 'H$_2$O 6.3 μm'),
             (2349, 'CO$_2$ 4.3 μm'), (3020, 'CH$_4$ 3.3 μm'), (3700, 'H$_2$O 2.7 μm')]
    for nu, lab in bands:
        ax.text(nu, 0.44, lab, rotation=90, ha='center', va='center',
                fontsize=8, color='#555555', alpha=0.9, zorder=6)

    # ---------------- panel (b): 8-14 um ----------------
    ax2 = fig.add_subplot(gs[1])
    x = z8['grid']
    ax2.plot(x, z8['tr_total'], color=C_TOT, lw=0.9, label='总透过率')
    for key, c in (('tr_H2O', C_H2O), ('tr_CO2', C_CO2), ('tr_CH4', C_CH4)):
        ax2.plot(x, z8[key], color=c, lw=0.55, alpha=0.85, label=LBL[key])
    ax2.set_xlim(700, 1250)
    ax2.set_ylim(0, 1.06)
    ax2.set_ylabel('斜程透过率  $T$')
    ax2.set_xlabel('波数 (cm$^{-1}$)')
    ax2b = top_wl_axis(ax2)
    ax2b.set_xticks([8, 9, 10, 11, 12, 13, 14])
    ax2b.set_xticklabels(['8', '9', '10', '11', '12', '13', '14'])
    ax2.grid(alpha=0.25, lw=0.5)
    ax2.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax2.text(0.008, 0.955, '(b) 8–14 μm 长波红外窗口（0.002 cm$^{-1}$ 分辨率）',
             transform=ax2.transAxes, fontsize=10.5, fontweight='bold', va='top',
             bbox=dict(facecolor='white', alpha=0.72, edgecolor='none', pad=1.6))
    ax2.legend(loc='lower right', ncol=2, fontsize=8.5, framealpha=0.9)

    # ---------------- panel (c): 3-5 um ----------------
    ax3 = fig.add_subplot(gs[2])
    x = z35['grid']
    ax3.plot(x, z35['tr_total'], color=C_TOT, lw=0.9, label='总透过率')
    for key, c in (('tr_H2O', C_H2O), ('tr_CO2', C_CO2), ('tr_CH4', C_CH4)):
        ax3.plot(x, z35[key], color=c, lw=0.55, alpha=0.85, label=LBL[key])
    ax3.set_xlim(2000, 3333)
    ax3.set_ylim(0, 1.06)
    ax3.set_ylabel('斜程透过率  $T$')
    ax3.set_xlabel('波数 (cm$^{-1}$)')
    ax3b = top_wl_axis(ax3)
    ax3b.set_xticks([3, 3.25, 3.5, 3.75, 4, 4.25, 4.5, 4.75, 5])
    ax3b.set_xticklabels(['3', '3.25', '3.5', '3.75', '4', '4.25', '4.5', '4.75', '5'])
    ax3.grid(alpha=0.25, lw=0.5)
    ax3.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax3.text(0.008, 0.955, '(c) 3–5 μm 中波红外（0.005 cm$^{-1}$ 分辨率）',
             transform=ax3.transAxes, fontsize=10.5, fontweight='bold', va='top',
             bbox=dict(facecolor='white', alpha=0.72, edgecolor='none', pad=1.6))
    ax3.legend(loc='lower right', ncol=2, fontsize=8.5, framealpha=0.9)

    f1 = os.path.join(OUTDIR, 'slant_transmittance_HITRAN2020.png')
    fig.savefig(f1)
    fig.savefig(f1.replace('.png', '.pdf'))
    print('saved', f1)

    # ---------------- figure 2: HITRAN line distribution ----------------
    fig2, axs = plt.subplots(3, 1, figsize=(12.0, 9.6), sharex=True,
                             gridspec_kw=dict(hspace=0.32, left=0.09, right=0.975,
                                              top=0.90, bottom=0.07))
    fig2.suptitle('HITRAN2020 谱线强度分布（每 2 cm$^{-1}$ 最强线，竖线为 S ≥ 10$^{-21}$ 的强线）',
                  fontsize=12.5, y=0.97)
    for a, mol, col, name in zip(axs, ('H2O', 'CO2', 'CH4'),
                                 (C_H2O, C_CO2, C_CH4),
                                 ('H$_2$O', 'CO$_2$', 'CH$_4$')):
        dd = np.load(os.path.join(BASE, 'lines', mol + '.npz'))
        nu, sw = dd['nu'], dd['sw']
        sel = (nu >= 500) & (nu <= 5000) & (sw >= 1e-28)
        nu, sw = nu[sel], sw[sel]
        bins = np.arange(500.0, 5000.1, 2.0)
        idx = np.digitize(nu, bins) - 1
        mx = np.full(bins.size - 1, 1e-30)
        np.maximum.at(mx, idx, sw)
        a.fill_between(0.5 * (bins[1:] + bins[:-1]), np.log10(mx), np.log10(1e-30),
                       color=col, alpha=0.35, lw=0, step='mid')
        strong = sw >= 1e-21
        a.vlines(nu[strong], np.log10(mx.max()) * 0 - 30, np.log10(sw[strong]),
                 color=col, lw=0.35, alpha=0.9)
        a.set_ylim(np.log10(1e-30), 0.5)
        a.set_yticks([-30, -25, -20, -15, -10, -5, 0])
        a.set_ylabel('lg[$S$]  (cm$^{-1}$/(molec·cm$^{-2}$))')
        a.set_xlim(500, 5000)
        a.grid(alpha=0.25, lw=0.5)
        a.text(0.008, 0.92, name, transform=a.transAxes, fontsize=11,
               fontweight='bold', va='top', color=col)
    axs[-1].set_xlabel('波数 (cm$^{-1}$)')
    axs[0].set_title('')
    ax2t = top_wl_axis(axs[0])
    ax2t.set_xticks(WLTICKS)
    ax2t.set_xticklabels(['%g' % w for w in WLTICKS])
    f2 = os.path.join(OUTDIR, 'hitran2020_line_sticks.png')
    fig2.savefig(f2)
    fig2.savefig(f2.replace('.png', '.pdf'))
    print('saved', f2)


if __name__ == '__main__':
    main()

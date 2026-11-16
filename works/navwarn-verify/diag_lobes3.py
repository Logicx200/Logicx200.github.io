# -*- coding: utf-8 -*-
"""Test: does the two-lobe split survive when (a) we integrate over the trail instead of
max, and (b) the contrast term is softened?"""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
R = rc.R
lons = np.arange(100, 116 + 1e-9, 0.2)
lats = np.arange(28, 44 + 1e-9, 0.2)
LON, LAT = np.meshgrid(lons, lats)
la, lo = np.radians(LAT), np.radians(LON)
obs = np.stack([R*np.cos(la)*np.cos(lo), R*np.cos(la)*np.sin(lo), R*np.sin(la)], axis=-1)

# precompute per-sample geometry
samples = []
for p in plume:
    ts = rc.T0 + p['t']
    dec, lonsub, _, _ = rc.sun_position(ts)
    ep = float(rc.sun_elev(p['lat'], p['lon'], dec, lonsub))
    beta = rc.horizon_dip(p['alt'])
    m = ep + beta
    L = 1/(1+math.exp(-(m-0.3)/1.2))
    d = rc.hav_km(LAT, LON, p['lat'], p['lon'])
    rp = R + p['alt']
    th = d/R
    elev = np.degrees(np.arctan2(rp*np.cos(th)-R, rp*np.sin(th)))
    V = 1-np.exp(-np.maximum(elev, 0)/4)
    la2, lo2 = np.radians(p['lat']), np.radians(p['lon'])
    pl = np.array([rp*math.cos(la2)*math.cos(lo2), rp*math.cos(la2)*math.sin(lo2), rp*math.sin(la2)])
    v = pl[None, None, :]-obs
    v = v/np.linalg.norm(v, axis=-1, keepdims=True)
    sun = np.array([math.cos(math.radians(dec))*math.cos(math.radians(lonsub)),
                    math.cos(math.radians(dec))*math.sin(math.radians(lonsub)),
                    math.sin(math.radians(dec))])
    sep = np.degrees(np.arccos(np.clip(np.sum(v*sun, axis=-1), -1, 1)))
    e_obs = rc.sun_elev(LAT, LON, dec, lonsub)
    D = 1/(1+np.exp((e_obs+6)/2.2))
    ok = (elev > 0) & (m > -0.5)
    samples.append(dict(D=D, L=L, V=V, sep=sep, ok=ok))


def field(mode, ccenter, cwidth):
    out = np.zeros(LAT.shape)
    for s in samples:
        C = 1/(1+np.exp(-(s['sep']-ccenter)/cwidth))
        q = np.where(s['ok'], s['D']*s['L']*s['V']*C, 0)
        if mode == 'max':
            out = np.maximum(out, q)
        else:
            out += q
    return out/out.max()


def profile(Q, lonx):
    j = int(np.argmin(np.abs(lons-lonx)))
    col = Q[:, j]
    peaks = [(round(float(lats[i]), 1), round(float(col[i]), 2)) for i in range(1, len(lats)-1)
             if col[i] >= col[i-1] and col[i] >= col[i+1] and col[i] > 0.55]
    neck = float(col.min())
    return peaks, round(neck, 2)


for mode in ('max', 'sum'):
    for cc, cw in [(35, 12), (30, 18), (25, 25), (20, 35)]:
        Q = field(mode, cc, cw)
        print(mode, 'C center %2d width %2d' % (cc, cw), '| lon106 peaks', profile(Q, 106)[0],
              'neck', profile(Q, 106)[1], '| lon108', profile(Q, 108)[0], profile(Q, 108)[1])

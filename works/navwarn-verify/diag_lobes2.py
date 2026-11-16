# -*- coding: utf-8 -*-
"""Is the two-lobe Q field an artifact of max-over-samples? Compare:
   A) max over samples (current)
   B) time-integrated sum over samples (observer sees the whole trail)
   C) max without the contrast factor C
"""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
R = rc.R
lons = np.arange(96, 120 + 1e-9, 0.4)
lats = np.arange(26, 46 + 1e-9, 0.4)
LON, LAT = np.meshgrid(lons, lats)
obs = rc.ecef_grid(LAT, LON, R) if hasattr(rc, 'ecef_grid') else None
if obs is None:
    la, lo = np.radians(LAT), np.radians(LON)
    obs = np.stack([R*np.cos(la)*np.cos(lo), R*np.cos(la)*np.sin(lo), R*np.sin(la)], axis=-1)

Qmax = np.zeros(LAT.shape)
Qsum = np.zeros(LAT.shape)
QnoC = np.zeros(LAT.shape)
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
    la, lo = np.radians(p['lat']), np.radians(p['lon'])
    pl = np.array([(R+p['alt'])*math.cos(la)*math.cos(lo), (R+p['alt'])*math.cos(la)*math.sin(lo), (R+p['alt'])*math.sin(la)])
    v = pl[None, None, :]-obs
    v = v/np.linalg.norm(v, axis=-1, keepdims=True)
    sun = np.array([math.cos(math.radians(dec))*math.cos(math.radians(lonsub)),
                    math.cos(math.radians(dec))*math.sin(math.radians(lonsub)),
                    math.sin(math.radians(dec))])
    sep = np.degrees(np.arccos(np.clip(np.sum(v*sun, axis=-1), -1, 1)))
    C = 1/(1+np.exp(-(sep-35)/12))
    e_obs = rc.sun_elev(LAT, LON, dec, lonsub)
    D = 1/(1+np.exp((e_obs+6)/2.2))
    base = D*L*V
    q = base*C
    q = np.where((elev > 0) & (m > -0.5), q, 0)
    Qmax = np.maximum(Qmax, q)
    Qsum += q
    QnoC = np.maximum(QnoC, np.where((elev > 0) & (m > -0.5), base, 0))

for name, Q in [('A max', Qmax), ('B sum', Qsum), ('C max-no-C', QnoC)]:
    Qn = Q/Q.max()
    # local maxima count (coarse)
    print('---', name, 'max %.3f' % Q.max())
    for lonx in (104, 106, 108, 110):
        j = int(np.argmin(np.abs(lons-lonx)))
        col = Qn[:, j]
        # find local maxima along lat
        peaks = [(lats[i], round(float(col[i]), 3)) for i in range(1, len(lats)-1)
                 if col[i] >= col[i-1] and col[i] >= col[i+1] and col[i] > 0.6]
        print('  lon=%d: peaks>0.6 %s' % (lonx, peaks))
    iy, ix = np.unravel_index(int(np.argmax(Qn)), Qn.shape)
    print('  global max at %.1fN %.1fE' % (LAT[iy, ix], LON[iy, ix]))
    # how many cells > 0.85 relative
    print('  area>0.85 rel: %d cells' % int((Qn > 0.85).sum()))

# -*- coding: utf-8 -*-
"""Prototype a continuous observation-quality field Q(lat,lon) in [0,1]."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
R = rc.R


def ecef(lat, lon, r):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([r * np.cos(la) * np.cos(lo), r * np.cos(la) * np.sin(lo), r * np.sin(la)], axis=-1)


def quality(LAT, LON, plume, DARK_CENTER=-6.0, DARK_W=2.2):
    Q = np.zeros(LAT.shape)
    obs = ecef(LAT, LON, R)
    for p in plume:
        ts = rc.T0 + p['t']
        dec, lonsub, _, _ = rc.sun_position(ts)
        ep = float(rc.sun_elev(p['lat'], p['lon'], dec, lonsub))
        beta = rc.horizon_dip(p['alt'])
        m = ep + beta
        Lf = 1.0 / (1.0 + math.exp(-(m - 0.3) / 1.2))
        d = rc.hav_km(LAT, LON, p['lat'], p['lon'])
        rp = R + p['alt']
        th = d / R
        elev = np.degrees(np.arctan2(rp * np.cos(th) - R, rp * np.sin(th)))
        Vf = 1.0 - np.exp(-np.maximum(elev, 0.0) / 4.0)
        pl = ecef(p['lat'], p['lon'], R + p['alt'])
        v = pl[None, None, :] - obs
        v = v / np.linalg.norm(v, axis=-1, keepdims=True)
        sun = np.array([math.cos(math.radians(dec)) * math.cos(math.radians(lonsub)),
                        math.cos(math.radians(dec)) * math.sin(math.radians(lonsub)),
                        math.sin(math.radians(dec))])
        sep = np.degrees(np.arccos(np.clip(np.sum(v * sun, axis=-1), -1, 1)))
        Cf = 1.0 / (1.0 + np.exp(-(sep - 35.0) / 12.0))
        e_obs = rc.sun_elev(LAT, LON, dec, lonsub)
        Df = 1.0 / (1.0 + np.exp((e_obs - DARK_CENTER) / DARK_W))
        q = Df * Lf * Vf * Cf
        q = np.where(elev > 0, q, 0.0)
        Q = np.maximum(Q, q)
    return Q


lons = np.arange(78, 128 + 1e-9, 0.25)
lats = np.arange(15, 55 + 1e-9, 0.25)
LON, LAT = np.meshgrid(lons, lats)
Q = quality(LAT, LON, plume)
print('Q max %.3f  mean %.3f  >0.5 %.2f%%  >0.2 %.2f%%' % (
    Q.max(), Q.mean(), 100 * (Q > .5).mean(), 100 * (Q > .2).mean()))
for p in (50, 75, 90, 95, 99):
    print(' p%d = %.3f' % (p, np.percentile(Q, p)))
print()
for name, la, lo in rc.CITIES:
    i = int((la - 15) / 0.25); j = int((lo - 78) / 0.25)
    print(' %-6s Q=%.3f' % (name, Q[i, j]))


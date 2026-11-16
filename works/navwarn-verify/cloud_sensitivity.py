# -*- coding: utf-8 -*-
"""Sensitivity of the rocket-cloud visible area to the empirical thresholds, T0 and
the viewing-direction (sun-angle) contrast gate."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
lons = np.arange(70, 140 + 1e-9, 0.25)
lats = np.arange(0, 60 + 1e-9, 0.25)
LON, LAT = np.meshgrid(lons, lats)
cell = (0.25 * 111.32 * np.cos(np.radians(LAT))) * (0.25 * 110.57)


def ecef(lat, lon, r_km):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([r_km * np.cos(la) * np.cos(lo),
                     r_km * np.cos(la) * np.sin(lo),
                     r_km * np.sin(la)], axis=-1)


def mask(thr, tshift_s, sun_sep_min=0.0):
    hit = np.zeros(LAT.shape, dtype=bool)
    obs = ecef(LAT, LON, rc.R)
    for p in plume:
        ts = rc.T0 + tshift_s + p['t']
        dec, lonsub, _, _ = rc.sun_position(ts)
        ep = float(rc.sun_elev(p['lat'], p['lon'], dec, lonsub))
        if ep <= -rc.horizon_dip(p['alt']):
            continue
        d = rc.hav_km(LAT, LON, p['lat'], p['lon'])
        within = d <= p['dmax']
        if not within.any():
            continue
        e_obs = rc.sun_elev(LAT, LON, dec, lonsub)
        m = within & (e_obs < thr)
        if sun_sep_min > 0:
            pl = ecef(p['lat'], p['lon'], rc.R + p['alt'])
            v = pl[None, None, :] - obs
            v /= np.linalg.norm(v, axis=-1, keepdims=True)
            sun = np.array([math.cos(math.radians(dec)) * math.cos(math.radians(lonsub)),
                            math.cos(math.radians(dec)) * math.sin(math.radians(lonsub)),
                            math.sin(math.radians(dec))])
            ang = np.degrees(np.arccos(np.clip(np.sum(v * sun, axis=-1), -1, 1)))
            m &= (ang > sun_sep_min)
        hit |= m
    return hit


print('threshold  area(x1e4 km2)   [observer sun < thr, plume sunlit, above horizon]')
for thr in (-6, -8, -10, -12):
    m = mask(thr, 0)
    print('  e_obs < %3d deg : %8.1f' % (thr, (m * cell).sum() / 1e4))
print()
print('T0 shift, threshold -6 deg')
for dt in (-180, -120, -60, 0, 60, 120, 180):
    m = mask(-6, dt)
    print('  T0 %+4.0f s : %8.1f' % (dt, (m * cell).sum() / 1e4))
print()
print('viewing-direction gate (threshold -6 deg): require angle(plume, sun) > X')
for ang in (0, 20, 40, 60, 80):
    m = mask(-6, 0, ang)
    print('  sep > %2d deg : %8.1f' % (ang, (m * cell).sum() / 1e4))
print()
# fraction of visible cells where the plume is below 5 deg elevation (marginal)
m = mask(-6, 0)
best_el = np.full(LAT.shape, -99.0)
for p in plume:
    d = rc.hav_km(LAT, LON, p['lat'], p['lon'])
    within = d <= p['dmax']
    if not within.any():
        continue
    th = np.radians(d / rc.R)
    rp = rc.R + p['alt']
    el = np.degrees(np.arctan2(rp * np.cos(th) - rc.R, rp * np.sin(th)))
    best_el = np.where(within, np.maximum(best_el, el), best_el)
print('visible area with plume elevation < 5 deg: %.1f x1e4 km2 (%.0f%% of visible)' % (
    ((m & (best_el < 5)) * cell).sum() / 1e4, 100 * ((m & (best_el < 5)) * cell).sum() / max(1, (m * cell).sum())))

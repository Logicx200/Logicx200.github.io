# -*- coding: utf-8 -*-
"""Diagnose the two-lobe structure of the Q field: which plume sample/factor dominates
at the two peaks and at the neck."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)
R = rc.R


def ecef(lat, lon, r):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([r*np.cos(la)*np.cos(lo), r*np.cos(la)*np.sin(lo), r*np.sin(la)], axis=-1)


def q_at(lat, lon, subset=None):
    """Return list of (q, t, alt, D,L,V,C, sun, sep, elev) for each sample."""
    out = []
    for p in (subset or plume):
        ts = rc.T0 + p['t']
        dec, lonsub, _, _ = rc.sun_position(ts)
        ep = float(rc.sun_elev(p['lat'], p['lon'], dec, lonsub))
        beta = rc.horizon_dip(p['alt'])
        m = ep + beta
        L = 1/(1+math.exp(-(m-0.3)/1.2))
        d = float(rc.hav_km(lat, lon, p['lat'], p['lon']))
        th = d/R
        rp = R + p['alt']
        elev = math.degrees(math.atan2(rp*math.cos(th)-R, rp*math.sin(th)))
        V = 1-math.exp(-max(elev, 0)/4)
        pl = ecef(np.array([p['lat']]), np.array([p['lon']]), R+p['alt'])[0]
        ob = ecef(np.array([lat]), np.array([lon]), R)[0]
        v = pl-ob; v = v/np.linalg.norm(v)
        sun = np.array([math.cos(math.radians(dec))*math.cos(math.radians(lonsub)),
                        math.cos(math.radians(dec))*math.sin(math.radians(lonsub)),
                        math.sin(math.radians(dec))])
        sep = math.degrees(math.acos(float(np.clip(np.dot(v, sun), -1, 1))))
        C = 1/(1+math.exp(-(sep-35)/12))
        e_obs = float(rc.sun_elev(lat, lon, dec, lonsub))
        D = 1/(1+math.exp((e_obs+6)/2.2))
        q = D*L*V*C
        if elev <= 0 or m <= -0.5:
            q = 0.0
        out.append(dict(q=q, t=p['t'], alt=p['alt'], D=D, L=L, V=V, C=C, e_obs=e_obs, sep=sep, elev=elev))
    out.sort(key=lambda x: -x['q'])
    return out


for name, la, lo in [('北峰', 40.0, 107.0), ('颈部', 36.0, 105.0), ('南峰', 32.0, 106.0),
                     ('包头', 40.66, 109.84), ('西安', 34.34, 108.94), ('成都', 30.57, 104.07)]:
    r = q_at(la, lo)
    top = r[:3]
    print(f'--- {name} ({la},{lo})  Qmax={top[0]["q"]:.3f}')
    for x in top:
        print('  t=%5.0f alt=%5.0f  q=%.3f  D=%.2f L=%.2f V=%.2f C=%.2f  sep=%4.0f elev=%4.1f  sun_e=%5.1f' % (
            x['t'], x['alt'], x['q'], x['D'], x['L'], x['V'], x['C'], x['sep'], x['elev'], x['e_obs']))

# Which phase dominates where?
print('\nDominant sample altitude vs latitude (lon=106):')
for la in range(28, 46, 2):
    r = q_at(la, 106.0)
    x = r[0]
    print('  lat=%2d  Q=%.3f  dominant t=%3.0fs alt=%3.0fkm  (D=%.2f L=%.2f V=%.2f C=%.2f)' % (
        la, x['q'], x['t'], x['alt'], x['D'], x['L'], x['V'], x['C']))

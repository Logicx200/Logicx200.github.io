# -*- coding: utf-8 -*-
"""For each city: best look at the sunlit plume, and the 3-D angle between the plume
line of sight and the Sun direction (contrast proxy: small angle = looking into the
bright twilight glow)."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import rocket_cloud as rc

ascent, src = rc.load_ascent()
plume = rc.plume_points(ascent)


def ecef(lat, lon, r):
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([r * math.cos(la) * math.cos(lo), r * math.cos(la) * math.sin(lo), r * math.sin(la)])


print('city      plume look(elev/az)  sun elev   plume-sun angle   verdict')
for name, la, lo in rc.CITIES:
    best = None
    for p in plume:
        el, az, slant = rc.look_angles(la, lo, p['lat'], p['lon'], p['alt'])
        if el <= 0:
            continue
        ts = rc.T0 + p['t']
        dec, lonsub, _, _ = rc.sun_position(ts)
        e_obs = float(rc.sun_elev(la, lo, dec, lonsub))
        if e_obs >= rc.DARK_VISIBLE:
            continue
        if best is None or el > best[0]:
            best = (el, p, e_obs, az, dec, lonsub)
    if not best:
        continue
    el, p, e_obs, az, dec, lonsub = best
    obs = ecef(la, lo, rc.R)
    pl = ecef(p['lat'], p['lon'], rc.R + p['alt'])
    v = pl - obs
    v /= np.linalg.norm(v)
    sun = np.array([math.cos(math.radians(dec)) * math.cos(math.radians(lonsub)),
                    math.cos(math.radians(dec)) * math.sin(math.radians(lonsub)),
                    math.sin(math.radians(dec))])
    sep = math.degrees(math.acos(float(np.clip(np.dot(v, sun), -1, 1))))
    verdict = '背向太阳，背景暗' if sep > 60 else ('一般' if sep > 35 else '正对晨光，对比度差')
    print('%-6s %5.1f° /%4.0f°   %6.1f°   %6.1f°  %s' % (name, el, az, e_obs, sep, verdict))

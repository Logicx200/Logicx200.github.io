# -*- coding: utf-8 -*-
"""Quantify: (a) deviation between the drawn (re-projected) ascent and the integrated one,
(b) point-in-polygon check of the modelled first-stage impact,
(c) independent 2D ballistic check of the 633 km first-stage range."""
import sys, types, math, json
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}; mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['mpl_toolkits.mplot3d'] = m3d
import trajectory3d as T

R = 6371.0088
LAT0, LON0 = 38.849, 111.608
AZ_fit = 188.77

def hav(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    return 2 * R * math.asin(math.sqrt(math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))

def dest(lat, lon, bearing, dist_km):
    la1, lo1 = map(math.radians, (lat, lon)); br, d = math.radians(bearing), dist_km / R
    la2 = math.asin(math.sin(la1)*math.cos(d) + math.cos(la1)*math.sin(d)*math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br)*math.sin(d)*math.cos(la1), math.cos(d)-math.sin(la1)*math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2)+540)%360-180

def inside(lat, lon, ring):
    # ray casting on lat/lon plane (fine at this scale)
    c = False
    n = len(ring)
    for i in range(n):
        y1, x1 = ring[i]; y2, x2 = ring[(i+1) % n]
        if ((y1 > lat) != (y2 > lat)) and (lon < (x2-x1)*(lat-y1)/(y2-y1)+x1):
            c = not c
    return c

print('=== A. project run (rate 0.28, target 650) ===')
T.thrust_dir.__defaults__ = (88.0, 0.28)
res = T.run(188.2, 650.0)
smp = res['samples']
print('events:', [(e['ev'], e['t']) for e in res['events']])
print('impact1:', res['impact1'])
print('last samples:')
for s in smp[-4:]:
    print('   ', s)

print('\n=== B. drawn ascent vs integrated ascent ===')
# replicate make_traj_layer mapping for t<=310
worst = (0, None)
for s in smp:
    t = float(s['t'])
    if t > 310: continue
    d = hav(LAT0, LON0, s['lat'], s['lon'])
    lat2, lon2 = dest(LAT0, LON0, AZ_fit, d)
    off = hav(s['lat'], s['lon'], lat2, lon2)
    if off > worst[0]:
        worst = (off, s)
    if t in (55.0, 155.0, 205.0, 255.0, 305.0):
        print(' t=%6.1f integrated=(%.4f,%.4f) -> drawn=(%.4f,%.4f) offset=%.1f km' %
              (t, s['lat'], s['lon'], lat2, lon2, off))
print(' max offset of drawn vs integrated ground track: %.1f km at t=%.1f' % (worst[0], worst[1]['t']))
print(' (this is what make_traj_layer.py silently replaces; note for t>205 the integrated ground track'
      ' turns ~10 deg east of the 188.8 great circle)')

print('\n=== C. is the modelled first-stage impact inside NOTAM box A5897? ===')
ring1 = [(33.566667, 110.516667), (33.533333, 110.733333), (33.166667, 110.683333), (33.183333, 110.45)]
ring2 = [(30.583333, 109.95), (30.55, 110.316667), (29.9, 110.216667), (29.95, 109.833333)]
imp = res['impact1']
print(' impact1 = %.4fN %.4fE, inside A5897 = %s' % (imp['lat'], imp['lon'], inside(imp['lat'], imp['lon'], ring1)))
print(' distance to A5897 centre = %.1f km' % hav(imp['lat'], imp['lon'], 33.3625, 110.595833))
c1 = (sum(p[0] for p in ring1)/4, sum(p[1] for p in ring1)/4)
print(' A5897 centre distance to launch = %.1f km' % hav(LAT0, LON0, *c1))

print('\n=== D. independent 2D ballistic propagation of the stage-1 state ===')
# separation state taken from the project trajectory: t=157 s (hard-coded event), alt 84.5, v 2.203, FPA?
# get FPA from the replica (same physics as project)
from analyze_model import simulate
rr = simulate(rate=0.28, fairing_t=200.0, dt=0.5, verbose=False)
sep_t, sep_r, sep_v, sep_m = rr['sep']
alt0 = np.linalg.norm(sep_r) - T.R
v0 = np.linalg.norm(sep_v)
up = sep_r / np.linalg.norm(sep_r)
fpa = math.degrees(math.asin(max(-1, min(1, np.dot(sep_v / v0, up)))))
print(' separation state: t=%.1f alt=%.2f km speed=%.4f km/s flight-path-angle=%.2f deg  (checked against project event 157/84.5/2.203)' % (
    sep_t, alt0/1000, v0/1000, fpa))

def ballistic2d(alt0_km, speed, fpa_deg, drag, cda=6.0, mass=15000.0, dt=0.02):
    r = R*1000 + alt0_km*1000
    th = 0.0
    vr = speed*math.sin(math.radians(fpa_deg))
    vt = speed*math.cos(math.radians(fpa_deg))
    t = 0.0
    while r > R*1000 and t < 5000:
        def deriv(r, th, vr, vt):
            v = math.hypot(vr, vt)
            g = -T.MU/r**2
            if drag:
                h = r - R*1000
                rho = 1.225*math.exp(-max(h,0)/8500.0) if h < 200e3 else 0.0
                ad = 0.5*rho*cda*v*v/mass
                ar = g - ad*vr/v
                at = -ad*vt/v
            else:
                ar, at = g, 0.0
            # polar equations
            ar_tot = ar + vt*vt/r
            at_tot = at - vr*vt/r
            return vr, vt/r, ar_tot, at_tot
        k1 = deriv(r, th, vr, vt)
        r2, th2, vr2, vt2 = r+dt/2*k1[0], th+dt/2*k1[1], vr+dt/2*k1[2], vt+dt/2*k1[3]
        k2 = deriv(r2, th2, vr2, vt2)
        r3, th3, vr3, vt3 = r+dt/2*k2[0], th+dt/2*k2[1], vr+dt/2*k2[2], vt+dt/2*k2[3]
        k3 = deriv(r3, th3, vr3, vt3)
        r4, th4, vr4, vt4 = r+dt*k3[0], th+dt*k3[1], vr+dt*k3[2], vt+dt*k3[3]
        k4 = deriv(r4, th4, vr4, vt4)
        r += dt/6*(k1[0]+2*k2[0]+2*k3[0]+k4[0])
        th += dt/6*(k1[1]+2*k2[1]+2*k3[1]+k4[1])
        vr += dt/6*(k1[2]+2*k2[2]+2*k3[2]+k4[2])
        vt += dt/6*(k1[3]+2*k2[3]+2*k3[3]+k4[3])
        t += dt
        if alt0_km > 0 and r < R*1000:
            break
    return math.degrees(th)*R*1000/1000, t, r/1000-R

for drag in (False, True):
    rng, t, alt = ballistic2d(alt0/1000, v0, fpa, drag)
    print(' vacuum' if not drag else ' with drag', '-> ground range %.1f km, flight time %.1f s' % (rng, t))
print(' project model reports first-stage impact 633.4 km (dt=0.5, rate 0.28)')
print('\n=== E. flat-earth analytic sanity check ===')
print(' v0^2*sin(2*fpa)/g = %.1f km  (flat, vacuum, g=9.5)' % ((v0/1000)**2*math.sin(2*math.radians(fpa))/9.5))

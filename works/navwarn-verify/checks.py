# -*- coding: utf-8 -*-
"""Independent checks: T0 timestamp, GMST, eci_to_geodetic longitude bug,
and sensitivity sweeps of the project's model (via its own physics functions)."""
import sys, types, math, datetime
import numpy as np

sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}
mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk; sys.modules['mpl_toolkits.mplot3d'] = m3d

import trajectory3d as T
from analyze_model import simulate, R

print('=== 1. T0 timestamp check ===')
t0 = 1763505870.0
print('hardcoded t0 unix =', t0)
print('-> UTC =', datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).isoformat())
print('trajectory.js t0_estimate = 2026-11-18T22:44:30+00:00')
print('.json t0_utc = 2026-11-18T22:44:30Z')
g = T.gmst(t0)
print('GMST(t0) = %.4f deg' % math.degrees(g))
# verify with an independent GMST (IAU 1982) implementation
def gmst_iau82(unix):
    jd = unix / 86400.0 + 2440587.5
    T_ = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T_**2 - T_**3 / 38710000.0
    return g % 360
print('independent GMST(t0) = %.4f deg' % gmst_iau82(t0))

print('\n=== 2. eci_to_geodetic longitude wrap bug ===')
# build a point whose ECI longitude is 190 deg, gmst 0
lon_eci = math.radians(190.0)
r = np.array([R * math.cos(math.radians(10)), R * math.sin(math.radians(10)), R * math.sin(math.radians(10))])
r2 = np.array([R * math.cos(math.radians(10)) * math.cos(lon_eci),
               R * math.cos(math.radians(10)) * math.sin(lon_eci),
               R * math.sin(math.radians(10))])
lat, lon, alt = T.eci_to_geodetic(r2, 0.0)
print('true geodetic lon = -170.0 deg ; project function returns lon =', round(lon, 4))
lon_eci = math.radians(190.0)
r3 = np.array([R * math.cos(math.radians(10)) * math.cos(lon_eci),
               R * math.cos(math.radians(10)) * math.sin(lon_eci), 0.0])
print('another test (lat=0, eci lon=190):', T.eci_to_geodetic(r3, 0.0)[:2])

print('\n=== 3. where the bug hits the committed orbit track (trajectory3d.json) ===')
import json
j = json.load(open(r'F:\DeepSeek工作区\navwarn-map\trajectory3d.json', encoding='utf-8'))
o = j['orbit']
for i in range(len(o) - 1):
    if abs(o[i + 1][1] - o[i][1]) > 100:
        print('  jump at index', i, ':', o[i], '->', o[i + 1], ' (true next lon would be %.2f)' % (o[i + 1][1] - 180))
print('  note: trajectory3d.json events:', [(e['ev'], e['t']) for e in j['events']])
print('  its impact1:', j['impact1'])
print('  its element i =', j['elements']['inc_deg'], ' e =', j['elements']['e'])
print('  but current trajectory3d.py run gives i=85.4-86.1, e=0.77-0.86 (see analyze_model.py)')

print('\n=== 4. great-circle relation: what inclination matches ground-track bearing 188.2 at 38.849N ===')
i_geo = math.degrees(math.acos(math.cos(math.radians(38.849)) * math.sin(math.radians(188.2))))
print('i = acos(cos(lat)*sin(az)) =', round(i_geo, 2))
print('ground-track bearing of a 96.4-deg orbit at 34.4N:',
      round(math.degrees(math.asin(math.cos(math.radians(i_geo)) / math.cos(math.radians(34.4)))), 2), '(this is the standard formula)')

print('\n=== 5. first-stage impact vs NOTAM boxes ===')
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return 2 * 6371.0088 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))
def brg(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360
site = (38.849, 111.608)
box1 = (33.3625, 110.59583333333333)
box2 = (30.245833333333334, 110.07916666666667)
print('box1: dist=%.1f km bearing=%.2f' % (hav(site, box1), brg(site, box1)))
print('box2: dist=%.1f km bearing=%.2f' % (hav(site, box2), brg(site, box2)))
print('box1-box2: dist=%.1f km bearing=%.2f' % (hav(box1, box2), brg(box1, box2)))

print('\n=== 6. sensitivity sweep (project model, dt=0.5 like the project) ===')
print('-- pitch rate (fairing t=200) --')
for rate in (0.22, 0.24, 0.26, 0.28, 0.30, 0.32):
    r = simulate(rate=rate, fairing_t=200.0, dt=0.5, verbose=False)
    imp = r['imp1']
    print(' rate=%.2f -> sep t=%.1f alt=%.2f v=%.3f i=%.2f | imp1 %.1fkm %.4fN %.4fE  dist_to_box1=%.1f km | fair %.1fkm | shut v=%.3f' % (
        rate, r['sep'][0], (np.linalg.norm(r['sep'][1]) - R) / 1000, np.linalg.norm(r['sep'][2]) / 1000,
        r['shutdown']['inc'], imp['downrange_km'], imp['lat'], imp['lon'],
        hav((imp['lat'], imp['lon']), box1), r['fair']['downrange_km'], r['shutdown']['v']))
print('-- fairing separation time (rate 0.28) --')
for ft in (175, 180, 185, 190, 195, 200, 205):
    r = simulate(rate=0.28, fairing_t=ft, dt=0.5, verbose=False)
    f = r['fair']
    print(' fairing_t=%d -> fairing sep alt=%.1f v=%.3f | impact %.1fkm %.4fN %.4fE dist_to_box2=%.1f km' % (
        ft, f['alt_km'], f['v_kms'], f['downrange_km'], f['lat'], f['lon'],
        hav((f['lat'], f['lon']), box2)))
print('-- stage1 drag area CdA (rate 0.28) --')
for cda in (3.0, 6.0, 12.0, 24.0):
    r = simulate(rate=0.28, fairing_t=200.0, stage1_cda=cda, dt=0.5, verbose=False)
    imp = r['imp1']
    print(' CdA1=%.1f -> imp1 %.1fkm %.4fN %.4fE dist_to_box1=%.1f km' % (
        cda, imp['downrange_km'], imp['lat'], imp['lon'], hav((imp['lat'], imp['lon']), box1)))
print('-- mass-consistent m0 (237100 kg) vs project 232000 --')
for m0v in (232000.0, 237100.0):
    r = simulate(rate=0.28, fairing_t=185.0, m0=m0v, dt=0.5, verbose=False)
    print(' m0=%.0f -> imp1 %.1fkm dist_box1=%.1f | fair %.1fkm dist_box2=%.1f | shut t=%.1f alt=%.1f v=%.3f i=%.2f e=%.3f rp=%.0f' % (
        m0v, r['imp1']['downrange_km'], hav((r['imp1']['lat'], r['imp1']['lon']), box1),
        r['fair']['downrange_km'], hav((r['fair']['lat'], r['fair']['lon']), box2),
        r['shutdown']['t'], r['shutdown']['alt'], r['shutdown']['v'], r['shutdown']['inc'],
        r['elements']['e'], r['elements']['rp_km']))
print('-- dt convergence with correct downrange --')
for dt in (0.5, 0.25, 0.1):
    r = simulate(rate=0.28, fairing_t=185.0, dt=dt, verbose=False)
    print(' dt=%.2f -> imp1 %.1fkm %.4fN %.4fE | fair %.1fkm | shut v=%.3f i=%.2f | elem a=%.0f e=%.3f rp=%.0f' % (
        dt, r['imp1']['downrange_km'], r['imp1']['lat'], r['imp1']['lon'],
        r['fair']['downrange_km'], r['shutdown']['v'], r['shutdown']['inc'],
        r['elements']['a_km'], r['elements']['e'], r['elements']['rp_km']))

# -*- coding: utf-8 -*-
"""Stub matplotlib, import the project's trajectory3d.py unchanged, run it, dump facts."""
import sys, types, json, math

# ---- stub matplotlib so trajectory3d.py imports without it ----
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}
for fn in ('figure', 'tight_layout', 'savefig', 'text2D', 'plot', 'scatter', 'legend', 'plot_wireframe', 'set_box_aspect'):
    setattr(plt, fn, lambda *a, **k: None)
mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl
sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
sys.modules['mpl_toolkits.mplot3d'] = m3d

sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
import trajectory3d as T

print('=== module constants ===')
print('R=', T.R, 'MU=', T.MU, 'OMEGA=', T.OMEGA, 'J2=', T.J2)
print('VEH=', T.VEH)
print('m0=', T.VEH['m0'],
      ' sum(m1p,m1d,m2p,m2d,payload,fairing)=',
      T.VEH['m1_prop'] + T.VEH['m1_dry'] + T.VEH['m2_prop'] + T.VEH['m2_dry'] + T.VEH['payload'] + T.VEH['fairing'])
print('mdot1=', T.VEH['T1'] / T.VEH['ve1'], ' burn1=', T.VEH['m1_prop'] / (T.VEH['T1'] / T.VEH['ve1']))
print('mdot2=', T.VEH['T2'] / T.VEH['ve2'], ' burn2=', T.VEH['m2_prop'] / (T.VEH['T2'] / T.VEH['ve2']))

print('\n=== run(188.2, 550.0) ===')
res = T.run(188.2, 550.0)
for e in res['events']:
    print(' event:', json.dumps(e, ensure_ascii=False))
print(' impact1:', res['impact1'])
print(' elements:', res['elements'])
print(' target_alt_km:', res['target_alt_km'])

print('\n=== selected samples ===')
want = {0.0: None, 5: None, 10: None, 50: None, 100: None, 120: None, 140: None, 145: None, 150: None, 151.5: None,
        155: None, 160: None, 170: None, 180: None, 185: None, 190: None, 200: None, 220: None, 240: None,
        260: None, 280: None, 300: None, 302: None, 305: None, 320: None, 400: None, 500: None, 600: None, 620: None, 640: None}
for s in res['samples']:
    if s['t'] in want:
        print('  sample:', s)

print('\n=== track of samples: distance/bearing from site ===')
lat0, lon0 = T.LAT0, T.LON0
for s in res['samples']:
    if int(s['t']) % 50 == 0:
        la1, lo1, la2, lo2 = map(math.radians, (lat0 * 180 / math.pi, lon0 * 180 / math.pi, s['lat'], s['lon']))
        d = 2 * T.R / 1000 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))
        y = math.sin(lo2 - lo1) * math.cos(la2)
        x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
        brg = (math.degrees(math.atan2(y, x)) + 360) % 360
        print(f"  t={s['t']:6.1f}  lat={s['lat']:8.4f} lon={s['lon']:9.4f} alt={s['alt_km']:8.2f} "
              f"v={s['v_kms']:6.3f}  dist={d:7.1f}km brg={brg:6.2f}")

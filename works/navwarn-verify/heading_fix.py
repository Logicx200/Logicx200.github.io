# -*- coding: utf-8 -*-
"""Test root cause of the ground-track bias: thrust_dir() projects the INITIAL heading vector
(a fixed direction in inertial space), instead of holding the Earth-relative azimuth at each
instant. Patch a copy to hold earth-relative azimuth=188.2 and compare."""
import sys, types, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}; mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['mpl_toolkits.mplot3d'] = m3d

src = open(r'F:\DeepSeek工作区\_navwarn_verify\tools\trajectory3d.py', encoding='utf-8').read()
OLD = '''def thrust_dir(t, r, d0, max_pitch=88.0, rate=0.30):
    up = unit(r)
    d = d0 - up * np.dot(d0, up)
    if np.linalg.norm(d) < 1e-9:
        return up
    d = unit(d)
    pitch = math.radians(min(max_pitch, max(0.0, (t - 10.0) * rate)))
    return math.cos(pitch) * up + math.sin(pitch) * d'''
NEW = '''def thrust_dir(t, r, d0, max_pitch=88.0, rate=0.30):
    """Hold the EARTH-RELATIVE azimuth 188.2 (recomputed from the current position)."""
    up = unit(r)
    east = unit(np.cross(np.array([0, 0, 1.0]), r))
    north = unit(np.cross(up, east))
    az = math.radians(188.2)
    d = math.cos(az) * north + math.sin(az) * east
    pitch = math.radians(min(max_pitch, max(0.0, (t - 10.0) * rate)))
    return math.cos(pitch) * up + math.sin(pitch) * d'''
assert OLD in src
src2 = src.replace(OLD, NEW)

def build(s, name):
    mod = types.ModuleType(name); mod.__dict__['__file__'] = name + '.py'
    exec(compile(s, name + '.py', 'exec'), mod.__dict__)
    return mod

def run(mod, rate, target=650.0):
    mod.thrust_dir.__defaults__ = (88.0, rate)
    return mod.run(188.2, target)

def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return 2*6371.0088*math.asin(math.sqrt(math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))
def brg(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    y = math.sin(lo2-lo1)*math.cos(la2)
    x = math.cos(la1)*math.sin(la2)-math.sin(la1)*math.cos(la2)*math.cos(lo2-lo1)
    return (math.degrees(math.atan2(y, x))+360)%360

site = (38.849, 111.608); box1 = (33.3625, 110.59583)
orig = build(src, 'traj_orig'); fixed = build(src2, 'traj_fixed')
print('sep event: ORIGINAL vs FIXED')
for rate in (0.26, 0.28, 0.30):
    a = run(orig, rate); b = run(fixed, rate)
    ia, ib = a['impact1'], b['impact1']
    print('rate=%.2f | orig sep %.1fs %.1fkm %.3fkm/s i=%.2f | imp1 %.1fkm (%.4f,%.4f) brg=%.2f dist_box1=%.1f' % (
        rate, a['events'][0]['t'], a['events'][0]['alt_km'], a['events'][0]['v_kms'], a['events'][0]['inc_deg'],
        ia['downrange_km'], ia['lat'], ia['lon'], brg(site, (ia['lat'], ia['lon'])), hav((ia['lat'], ia['lon']), box1)))
    print('          | fixed sep %.1fs %.1fkm %.3fkm/s i=%.2f | imp1 %.1fkm (%.4f,%.4f) brg=%.2f dist_box1=%.1f' % (
        b['events'][0]['t'], b['events'][0]['alt_km'], b['events'][0]['v_kms'], b['events'][0]['inc_deg'],
        ib['downrange_km'], ib['lat'], ib['lon'], brg(site, (ib['lat'], ib['lon'])), hav((ib['lat'], ib['lon']), box1)))

print('\nfixed version events (rate 0.28):')
b = run(fixed, 0.28)
for e in b['events']:
    print('  ', e['ev'], 't=', e.get('t'), 'alt=', e.get('alt_km'), 'v=', e.get('v_kms'),
          'impact=', e.get('impact', {}).get('downrange_km') if e.get('impact') else '',
          'i=', e.get('elements', {}).get('inc_deg', e.get('inc_deg')))
print('fixed elements:', b['elements'])

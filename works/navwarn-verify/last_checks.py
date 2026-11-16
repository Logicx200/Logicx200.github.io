# -*- coding: utf-8 -*-
import sys, types, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}; mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
m3 = types.ModuleType('mpl_toolkits.mplot3d'); m3.Axes3D = object
sys.modules['mpl_toolkits.mplot3d'] = m3
import trajectory3d as T
from analyze_model import simulate, R

def inside(lat, lon, ring):
    c = False
    for i in range(len(ring)):
        y1, x1 = ring[i]; y2, x2 = ring[(i+1) % len(ring)]
        if ((y1 > lat) != (y2 > lat)) and (lon < (x2-x1)*(lat-y1)/(y2-y1)+x1):
            c = not c
    return c
ring2 = [(30.583333, 109.95), (30.55, 110.316667), (29.9, 110.216667), (29.95, 109.833333)]
print('fairing candidate impacts vs A5898:')
for name, p in [('185.5s@0.28', (30.6453, 110.2915)), ('187.5s@0.28', (30.3480, 110.2818)),
                ('188.5s@0.28', (30.2258, 110.2780)), ('185.5s@0.30', (30.3930, 110.2456))]:
    print('  ', name, p, 'inside =', inside(p[0], p[1], ring2))

print('\n=== final coast point of the integration (rate 0.28, target 650) ===')
rr = simulate(rate=0.28, fairing_t=200.0, dt=0.5, verbose=False)
# log entries are (t, r, v, m); find last one and convert
t_last, r_last, v_last, m_last = rr['log'][-1]
th = T.gmst(1763505870.0)
lat, lon, alt = T.eci_to_geodetic(r_last, th + T.OMEGA * t_last)
print(' last logged coast point: t=%.1f lat=%.3f lon=%.3f alt=%.1f km v=%.2f km/s' % (t_last, lat, lon, alt/1000, np.linalg.norm(v_last)/1000))
# ground distance/bearing from site
def hav_brg(p, q):
    la1, lo1, la2, lo2 = map(math.radians, [p[0], p[1], q[0], q[1]])
    d = 2 * 6371.0088 * math.asin(math.sqrt(math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2))
    y = math.sin(lo2-lo1)*math.cos(la2); x = math.cos(la1)*math.sin(la2)-math.sin(la1)*math.cos(la2)*math.cos(lo2-lo1)
    return d, (math.degrees(math.atan2(y, x))+360)%360
d, b = hav_brg((38.849, 111.608), (lat, lon))
print(' -> %.1f km from Taiyuan, bearing %.2f (drawn "inferred insertion point" is at 1150 km)' % (d, b))

# how far downrange is the actual 650 km point? integrate a few seconds more to target alt
print('\n note: coast loop exits when alt>=650; last logged point alt=%.1f km at t=%.1f s' % (alt/1000, t_last))

# -*- coding: utf-8 -*-
import sys, types
sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}; mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk; sys.modules['mpl_toolkits.mplot3d'] = m3d

src = open(r'F:\DeepSeek工作区\_navwarn_verify\tools\trajectory3d.py', encoding='utf-8').read()

def run_variant(fairing_t, rate, m0=None, az=188.2, target=650.0):
    s = src.replace('if not fairing_done and t > 200:', 'if not fairing_done and t > %r:' % fairing_t)
    if m0 is not None:
        s = s.replace('m0=232000.0', 'm0=%r' % m0)
    mod = types.ModuleType('trajpatch2'); mod.__dict__['__file__'] = 'trajpatch2.py'
    exec(compile(s, 'trajpatch2.py', 'exec'), mod.__dict__)
    mod.thrust_dir.__defaults__ = (88.0, rate)
    res = mod.run(az, target)
    out = {}
    for e in res['events']:
        out[e['ev']] = e
    return out, res

def hav(a, b):
    import math
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return 2 * 6371.0088 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))

box2 = (30.245833333333334, 110.07916666666667)
print('target: fairing impact ~967 km at', box2)
for rate in (0.24, 0.26, 0.28, 0.30, 0.32):
    out, res = run_variant(185.0, rate)
    sep = out.get('一级关机/分离'); fair = out.get('整流罩分离')
    print(' rate=%.2f  fairing(sep %s) -> %.1f km %.4fN %.4fE  dist_box2=%.1f km | sep1 %.1fkm' % (
        rate, fair['t'], fair['impact']['downrange_km'], fair['impact']['lat'], fair['impact']['lon'],
        hav((fair['impact']['lat'], fair['impact']['lon']), box2),
        (out['一级关机/分离']['alt_km'])))
print()
for dt_ignore in (0,):
    pass
# what fairing_t exactly matches box2 with rate 0.28
print('scan fairing_t (rate 0.28):')
best = None
for ft in [round(180 + 0.5 * i, 1) for i in range(0, 25)]:
    out, res = run_variant(ft, 0.28)
    fair = out['整流罩分离']
    d = hav((fair['impact']['lat'], fair['impact']['lon']), box2)
    print('  t=%.1f -> %.1f km %.4fN %.4fE dist=%.1f' % (ft, fair['impact']['downrange_km'],
                                                        fair['impact']['lat'], fair['impact']['lon'], d))
    if best is None or d < best[1]:
        best = (ft, d)
print(' best fairing_t =', best)

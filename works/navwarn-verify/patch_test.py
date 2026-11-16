# -*- coding: utf-8 -*-
"""Patch a COPY of trajectory3d.py (fairing separation time / fairing ballistic coeff) and run it,
to check whether the README's fairing numbers are reproducible from the shipped code."""
import sys, types, re, math

sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}
mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk; sys.modules['mpl_toolkits.mplot3d'] = m3d

src = open(r'F:\DeepSeek工作区\_navwarn_verify\tools\trajectory3d.py', encoding='utf-8').read()
print('original fairing lines:')
for ln in src.splitlines():
    if 'fairing_done' in ln or 'rk4(rf' in ln or 'tf < t' in ln:
        print('   ', ln.strip())

def run_variant(fairing_t, fairing_mass, fairing_cda, rate=0.28):
    s = src
    s = s.replace('if not fairing_done and t > 200:', 'if not fairing_done and t > %r:' % fairing_t)
    s = s.replace('rk4(rf, vf, 600.0, np.zeros(3), 0, 2.5, dt)',
                  'rk4(rf, vf, %r, np.zeros(3), 0, %r, dt)' % (fairing_mass, fairing_cda))
    mod = types.ModuleType('trajpatch')
    mod.__dict__['__file__'] = 'trajpatch.py'
    exec(compile(s, 'trajpatch.py', 'exec'), mod.__dict__)
    mod.thrust_dir.__defaults__ = (88.0, rate)
    res = mod.run(188.2, 650.0)
    for e in res['events']:
        if e['ev'] == '整流罩分离':
            return e['t'], e['alt_km'], e['impact']
    return None

print('\n=== fairing variants (target 650, rate 0.28) ===')
for ft, fm, fc in [(200, 600, 2.5), (185, 600, 2.5), (185, 1500, 2.5), (185, 600, 1.5), (185, 1500, 12.0),
                   (187.5, 600, 2.5), (190, 600, 2.5)]:
    t, alt, imp = run_variant(ft, fm, fc)
    print(' fairing_t=%.1f mass=%.0f CdA=%.1f -> sep t=%.1f alt=%.1f | impact %.1f km  %.4fN %.4fE' %
          (ft, fm, fc, t, alt, imp['downrange_km'], imp['lat'], imp['lon']))

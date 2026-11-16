# -*- coding: utf-8 -*-
"""Run the project's make_traj_layer.main() unchanged (in the copied tree) and compare with
the committed traj3d.js. Also run trajectory3d with the same patched defaults to expose the
numbers behind traj3d.js."""
import sys, types, json, os, math, importlib

HERE = r'F:\DeepSeek工作区\_navwarn_verify\tools'
sys.path.insert(0, HERE)

mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}
mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl
sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
sys.modules['mpl_toolkits.mplot3d'] = m3d

import trajectory3d as T
import make_traj_layer as M

# ---- reproduce make_traj_layer exactly ----
M.main()
gen_path = os.path.join(os.path.dirname(HERE), 'traj3d.js')
gen = json.loads(open(gen_path, encoding='utf-8').read().split('=', 1)[1].strip().rstrip(';'))
proj = json.loads(open(r'F:\DeepSeek工作区\navwarn-map\traj3d.js', encoding='utf-8').read().split('=', 1)[1].strip().rstrip(';'))

print('\n=== generated vs committed traj3d.js ===')
for k in ('site', 'azimuth', 'azimuth_model', 'elements', 'note'):
    print(k, 'gen:', gen[k], '| proj:', proj[k])
print('ascent len gen/proj:', len(gen['ascent']), len(proj['ascent']))
print('gen last ascent:', gen['ascent'][-1], '| proj last:', proj['ascent'][-1])
print('gen events:')
for e in gen['events']:
    print('   ', e)
print('proj events:')
for e in proj['events']:
    print('   ', e)
# max diff of ascent arrays
if len(gen['ascent']) == len(proj['ascent']):
    d = max(max(abs(a - b) for a, b in zip(ga, pa)) for ga, pa in zip(gen['ascent'], proj['ascent']))
    print('max ascent component diff:', d)

print('\n=== underlying samples of the run used by make_traj_layer (rate 0.28, target 650) ===')
res = T.run(M.AZ, 650.0)
for s in res['samples']:
    if s['t'] in (140, 145, 150, 155, 157, 160, 180, 185, 190, 200, 205, 250, 280, 300, 305, 310):
        print('  ', s)
for e in res['events']:
    print('  event:', json.dumps(e, ensure_ascii=False, default=str))
print('  impact1:', res['impact1'])

# -*- coding: utf-8 -*-
"""诊断形态键内容与关键帧是否有效。"""
import bpy
import numpy as np

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
fo = bpy.data.objects['Flow_surface']
sk = fo.data.shape_keys
kbs = sk.key_blocks
print('形态键 %d 个, 动画数据=%s' % (len(kbs), sk.animation_data is not None))

base = np.empty(len(fo.data.vertices) * 3, dtype=np.float32)
kbs['Basis'].data.foreach_get('co', base)
base = base.reshape(-1, 3)

for nm in ['Basis', 't0000', 't0200', 't0600', 't1200']:
    kb = kbs.get(nm)
    if kb is None:
        print('  %-8s 不存在' % nm); continue
    co = np.empty(len(fo.data.vertices) * 3, dtype=np.float32)
    kb.data.foreach_get('co', co)
    co = co.reshape(-1, 3)
    dz = co[:, 2] - base[:, 2]
    print('  %-8s value=%.2f  dz_max=%8.2f  dz>1m 的顶点=%6d  当前求值value=%.2f'
          % (nm, kb.value, dz.max(), int((dz > 1).sum()), kb.value))

# 检查关键帧曲线
ad = sk.animation_data
if ad and ad.action:
    fc = [f for f in ad.action.fcurves if 'key_blocks' in f.data_path]
    print('fcurve 数 %d' % len(fc))
    for f in fc[:3]:
        print('  %s  keys=%d' % (f.data_path, len(f.keyframe_points)))
    # 取 t0600 的曲线看看
    target = None
    for f in fc:
        if 't0600' in f.data_path:
            target = f; break
    if target:
        kp = target.keyframe_points
        print('  t0600 关键帧: %s' % [(int(k.co[0]), round(k.co[1], 2)) for k in kp])
    else:
        print('  未找到 t0600 曲线')

# 逐帧求值, 看 z 最大值是否随时间变化
print()
print('帧 -> 求值后 z_max / dz_max:')
dg = bpy.context.evaluated_depsgraph_get()
for f in [0, 1, 5, 10, 30, 60, 100, 120]:
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = fo.evaluated_get(dg)
    me = ev.to_mesh()
    z = np.array([v.co.z for v in me.vertices])
    print('  f=%3d  z_max=%9.1f  dz_max=%7.1f  变形顶点=%6d'
          % (f, z.max(), (z - base[:, 2]).max(), int((np.abs(z - base[:, 2]) > 1).sum())))
    ev.to_mesh_clear()

# -*- coding: utf-8 -*-
"""最小测试: 搞清形态键关键帧的插值语义。"""
import bpy
import numpy as np

bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new('t')
me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
me.update()
ob = bpy.data.objects.new('t', me)
bpy.context.scene.collection.objects.link(ob)
sc = bpy.context.scene
sc.frame_end = 4

# 三个形态键: A 在 f0 为 1, B 在 f1 为 1, C 在 f2 为 1; 各自"跟随到下一帧"
for name, f in [('A', 0), ('B', 1), ('C', 2)]:
    kb = ob.shape_key_add(name=name, from_mix=False)
    for k in range(3):
        kb.data[k].co = (k, k, (10 if name == 'A' else 0) + (100 if name == 'B' else 0) + (1000 if name == 'C' else 0))
    kb.value = 0.0

kbs = ob.data.shape_keys.key_blocks
n = 3
frames = [0, 1, 2]
for i, name in enumerate(['A', 'B', 'C']):
    kb = kbs[name]
    kb.value = 1.0
    kb.keyframe_insert('value', frame=frames[i])
    kb.value = 0.0
    kb.keyframe_insert('value', frame=frames[i] + 1)

# 直接读关键帧, 不经过求值
print('--- 关键帧原始值 ---')
ad = ob.data.shape_keys.animation_data
for fc in ad.action.fcurves:
    print('%-40s %s' % (fc.data_path, [(int(k.co[0]), round(k.co[1], 3)) for k in fc.keyframe_points]))

print()
print('--- 逐帧求值: 顶点0的 z (A=10, B=100, C=1000) ---')
dg = bpy.context.evaluated_depsgraph_get()
for f in range(0, 5):
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    m2 = ev.to_mesh()
    z = m2.vertices[0].co.z
    vals = {k.name: round(k.value, 3) for k in kbs}
    print('  f=%d  z=%8.2f   value=%s' % (f, z, vals))
    ev.to_mesh_clear()

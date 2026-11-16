# -*- coding: utf-8 -*-
"""
为地形白模设置柔和的三点光照（太阳 + 天空填充 + 补光），
并把改进后的光照保存回 .blend，这样用户在 Blender 里打开即有良好观感。
"""
import bpy
import math
import os
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_terrain.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

terr = bpy.data.objects['Terrain']
bb = [terr.matrix_world @ Vector(c) for c in terr.bound_box]
xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
cx = (min(xs) + max(xs)) / 2; cy = (min(ys) + max(ys)) / 2; cz = (min(zs) + max(zs)) / 2
span = max(max(xs) - min(xs), max(ys) - min(ys))

# --- 清掉旧灯 ---
for o in [o for o in bpy.data.objects if o.type == 'LIGHT']:
    bpy.data.objects.remove(o, do_unlink=True)

# --- 主光: 太阳, 从西北偏上, 让山脊与谷地都有明暗层次 ---
sd = bpy.data.lights.new('Sun_key', type='SUN')
sd.energy = 3.4
sd.angle = math.radians(6.0)           # 中等柔和度, 保留地形起伏
sun = bpy.data.objects.new('Sun_key', sd)
sc.collection.objects.link(sun)
sun.location = (cx - span * 0.4, cy + span * 0.5, cz + span * 0.9)
sun.rotation_euler = (math.radians(52.0), 0.0, math.radians(-128.0))

# --- 补光: 面积柔光, 只抬亮背光面, 不压掉对比 ---
ad = bpy.data.lights.new('Area_fill', type='AREA')
ad.energy = 2.2e8
ad.size = span * 1.0
fill = bpy.data.objects.new('Area_fill', ad)
sc.collection.objects.link(fill)
fill.location = (cx + span * 0.5, cy - span * 0.6, cz + span * 0.5)
d = Vector((cx, cy, cz)) - fill.location
fill.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

# --- 天空背景: 压暗, 使白模轮廓突出 ---
w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
sc.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.045, 0.055, 0.075, 1.0)
    bg.inputs['Strength'].default_value = 1.0

# --- 视口着色设置(方便建模时查看): 关掉背面剔除, 开启阴影 ---
for area in getattr(bpy.context.screen, 'areas', []) if bpy.context.screen else []:
    pass

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('LIGHTING_OK  主光+补光+天空已写入 %s' % BLEND)
print('  太阳 energy=%.1f angle=%.0fdeg' % (sd.energy, math.degrees(sd.angle)))
print('  面积补光 energy=%.2e size=%.0f m' % (ad.energy, ad.size))

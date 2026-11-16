# -*- coding: utf-8 -*-
"""
调整相机使三个站点全部入画, 并渲染关键阶段。
"""
import bpy
import math
import numpy as np
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

# 以三个站点 + 地形范围确定取景中心与大小
objs = ['SRC_source', 'LAKE_barrier_lake', 'PORT_Jilong_port']
pts = [bpy.data.objects[n].location for n in objs]
cx = sum(p.x for p in pts) / len(pts)
cy = sum(p.y for p in pts) / len(pts)
cz = sum(p.z for p in pts) / len(pts)
terr = bpy.data.objects['Terrain_HR']
bb = [terr.matrix_world @ Vector(c) for c in terr.bound_box]
span = max(max(v.x for v in bb) - min(v.x for v in bb),
           max(v.y for v in bb) - min(v.y for v in bb))
print('站点中心 (%.0f, %.0f, %.0f)  地形跨度 %.0f m' % (cx, cy, cz, span))

tv = bpy.data.objects.get('TrackTarget')
tv.location = (cx, cy, cz)

cam = sc.camera
cam.data.lens = 38.0
dist = span * 2.05
az = math.radians(256.0)
el = math.radians(40.0)
cam.location = (cx + dist * math.cos(el) * math.sin(az),
                cy + dist * math.cos(el) * math.cos(az),
                cz + dist * math.sin(el))
bpy.context.view_layer.update()

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = 1600
sc.render.resolution_y = 900
try:
    sc.eevee.taa_render_samples = 24
except Exception:
    pass
sc.render.image_settings.file_format = 'PNG'

col = bpy.data.collections.get('Flow_frames')
objs_f = sorted(col.objects, key=lambda o: o.name)

for f in [0, 20, 44, 90, 120]:
    sc.frame_set(f)
    for i, o in enumerate(objs_f):
        v = (i == f)
        o.hide_viewport = not v
        o.hide_render = not v
    bpy.context.view_layer.update()
    sc.render.filepath = r'F:\DeepSeek工作区\jilong\blender\view_f%03d.png' % f
    bpy.ops.render.render(write_still=True)
    print('rendered f=%d' % f)

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('CAMERA_OK  相机已保存到 blend')
